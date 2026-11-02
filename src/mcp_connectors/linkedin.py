"""Read-only bridge to the optional, independently managed LinkedIn MCP server."""
import asyncio
from dataclasses import dataclass
import json
import os
import re
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from mcp import Client
from pydantic import Field, StringConstraints, field_validator

from .models import Model


TOOLS = frozenset({"search_jobs", "get_job_details", "get_person_profile",
                   "get_company_profile"})


class LinkedInJobSearch(Model):
    keywords: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default="Lithuania", min_length=1, max_length=200)
    include_remote_abroad: bool = True
    remote_locations: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]] = Field(
        default_factory=lambda: ["Europe"], min_length=1, max_length=3)
    max_pages: int = Field(default=1, ge=1, le=3, strict=True)
    date_posted: Literal["past_hour", "past_24_hours", "past_week", "past_month"] | None = None
    job_type: Literal["full_time", "part_time", "contract", "temporary", "volunteer", "internship", "other"] | None = None
    experience_level: Literal["internship", "entry", "associate", "mid_senior", "director", "executive"] | None = None
    work_type: Literal["on_site", "remote", "hybrid"] | None = None
    easy_apply: bool = False
    sort_by: Literal["relevance", "date"] | None = None

    @field_validator("keywords", "location", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value


def search_plan(options: LinkedInJobSearch) -> list[dict]:
    """Use the location/work-type query syntax observed in redesigned LinkedIn search."""
    common = options.model_dump(exclude_none=True, exclude={
        "keywords", "location", "work_type", "include_remote_abroad", "remote_locations"})
    scopes = [("regional", options.location, options.work_type)]
    if options.include_remote_abroad:
        scopes.extend(("remote", location, "remote") for location in options.remote_locations)
    plan = []
    seen = set()
    for scope, location, work_type in scopes:
        query = options.keywords
        word = {"remote": "remote", "hybrid": "hybrid", "on_site": "on-site"}.get(work_type)
        if word and not re.match(rf"^{re.escape(word)}\b", query, re.IGNORECASE):
            query = word + " " + query
        if location and not query.casefold().endswith(" in " + location.casefold()):
            query += " in " + location
        if query.casefold() not in seen:
            seen.add(query.casefold())
            plan.append({"scope": scope, "location": location, "work_type": work_type,
                         "arguments": {**common, "keywords": query}})
    return plan


@dataclass(frozen=True)
class LinkedInSettings:
    url: str | None = None
    timeout_s: int = 210

    def __post_init__(self):
        if not 1 <= self.timeout_s <= 600:
            raise ValueError("MCP_LINKEDIN_TIMEOUT_SECONDS must be between 1 and 600")
        if self.url is not None:
            parts = urlsplit(self.url)
            if (parts.scheme != "http" or parts.hostname != "127.0.0.1"
                    or parts.username is not None or parts.password is not None
                    or parts.path != "/mcp" or parts.query or parts.fragment
                    or parts.port is None or not 1 <= parts.port <= 65535
                    or re.search(r"[\s\\]", self.url)):
                raise ValueError("MCP_LINKEDIN_URL must be http://127.0.0.1:<port>/mcp")

    @classmethod
    def from_env(cls):
        return cls(os.getenv("MCP_LINKEDIN_URL") or None,
                   int(os.getenv("MCP_LINKEDIN_TIMEOUT_SECONDS", "210")))


class LinkedInResult(Model):
    source: Literal["linkedin"] = "linkedin"
    status: Literal["ok", "empty", "partial", "disabled", "upstream_error", "network_error", "timeout"]
    data: dict[str, Any] | None = None
    content: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None


class LinkedInBridge:
    def __init__(self, settings: LinkedInSettings):
        self.settings = settings
        self._lock = asyncio.Lock()

    def describe(self) -> dict:
        return {
            "id": "linkedin", "name": "LinkedIn MCP", "category": "professional",
            "website": "https://www.linkedin.com",
            "status": "implemented", "configured": self.settings.url is not None,
            "integration": "external-mcp", "live_status": "unverified",
            "job_search_defaults": {"location": "Lithuania", "include_remote_abroad": True,
                                    "remote_locations": ["Europe"]},
            "tools": ["linkedin_status"] + ["linkedin_" + name for name in sorted(TOOLS)],
        }

    async def search_jobs(self, options: LinkedInJobSearch) -> LinkedInResult:
        """Keep regional and international remote searches separate, retaining failures."""
        if self.settings.url is None:
            return await self.call("search_jobs")
        searches = []
        ids = []
        sections = {}
        scopes_by_job = {}
        deadline = asyncio.get_running_loop().time() + self.settings.timeout_s
        for index, plan in enumerate(search_plan(options)):
            remaining = deadline - asyncio.get_running_loop().time()
            attempts = 0
            try:
                if remaining <= 0:
                    raise TimeoutError
                async with asyncio.timeout(remaining):
                    attempts += 1
                    result = await self.call("search_jobs", plan["arguments"])
                    initial = search_data(result)
                    if (result.status == "ok" and initial is not None
                            and initial.get("job_ids") == [] and not initial.get("section_errors")):
                        # The upstream can capture only the navigation shell while AI results load.
                        await asyncio.sleep(1)
                        attempts += 1
                        result = await self.call("search_jobs", plan["arguments"])
            except TimeoutError:
                result = LinkedInResult(status="timeout", error="The combined LinkedIn search deadline expired.")
            data = search_data(result)
            scope_key = f"{plan['scope']}_{index + 1}"
            scope_ids = data.get("job_ids", []) if data else []
            errors = data.get("section_errors", {}) if data else {}
            scope_sections = data.get("sections", {}) if data else {}
            valid_ids = isinstance(scope_ids, list) and all(
                isinstance(job_id, str) and re.fullmatch(r"[0-9]{1,30}", job_id) for job_id in scope_ids)
            valid_sections = isinstance(scope_sections, dict) and all(
                isinstance(name, str) and isinstance(text, str) for name, text in scope_sections.items())
            if not valid_ids:
                scope_ids = []
            if not valid_sections:
                scope_sections = {}
            no_matches = (isinstance(errors, dict) and bool(errors) and all(
                isinstance(error, dict) and error.get("error_type") == "no_matching_jobs"
                for error in errors.values()))
            status = result.status
            evidence = None
            error = result.error
            if result.status == "ok":
                if data is None or not valid_ids or not valid_sections or not isinstance(errors, dict):
                    status = "partial" if scope_ids else "upstream_error"
                    error = "LinkedIn returned an invalid search payload."
                elif not scope_ids:
                    status = "empty" if no_matches else "upstream_error"
                    error = None if no_matches else "LinkedIn returned no job IDs and no explicit no-matches evidence."
                else:
                    status = "partial" if errors else "ok"
                    if plan["location"]:
                        text = scope_sections.get("search_results", "")
                        header = [line.strip() for line in text.splitlines() if line.strip()][:8]
                        evidence = next((line for line in header if line.casefold() == plan["location"].casefold()), None)
                        if evidence is None:
                            status, error = "partial", "The requested location was not confirmed in the search header."
            searches.append({**{key: value for key, value in plan.items() if key != "arguments"},
                             "key": scope_key, "query": plan["arguments"]["keywords"],
                             "status": status, "attempts": attempts, "location_evidence": evidence,
                             "data": data, "content": result.content, "error": error})
            for name, text in scope_sections.items():
                sections[f"{scope_key}.{name}"] = text
            for job_id in scope_ids:
                if job_id not in scopes_by_job:
                    ids.append(job_id)
                    scopes_by_job[job_id] = []
                if scope_key not in scopes_by_job[job_id]:
                    scopes_by_job[job_id].append(scope_key)
        failures = [search for search in searches if search["status"] not in {"ok", "empty"}]
        if failures:
            status = "partial" if ids else failures[0]["status"]
        else:
            status = "ok" if ids else "empty"
        return LinkedInResult(status=status, data={"job_ids": ids, "sections": sections,
            "searches": searches, "job_scopes": scopes_by_job,
            "remote_eligibility": "Search matches do not establish hiring-country eligibility; read each posting."},
            error="Some LinkedIn searches were incomplete; inspect searches and section_errors." if failures else None)

    async def call(self, name: str, arguments: dict | None = None) -> LinkedInResult:
        if name not in TOOLS and name != "status":
            raise ValueError("Unsupported LinkedIn tool")
        if self.settings.url is None:
            return LinkedInResult(status="disabled", error=(
                "LinkedIn MCP is not configured. Run scripts/linkedin.ps1 -Action Setup, "
                "then Login and Run; set MCP_LINKEDIN_URL=http://127.0.0.1:8001/mcp "
                "and restart MCP Connectors."))
        phase = "waiting for the local request slot"
        try:
            async with asyncio.timeout(self.settings.timeout_s):
                async with self._lock:
                    phase = "connecting to the local LinkedIn MCP server"
                    async with Client(self.settings.url, read_timeout_seconds=self.settings.timeout_s) as client:
                        if name == "status":
                            phase = "listing the upstream tools"
                            available = {tool.name for tool in (await client.list_tools()).tools}
                            missing = sorted(TOOLS - available)
                            return LinkedInResult(
                                status="upstream_error" if missing else "ok",
                                data={"reachable": True, "missing_tools": missing,
                                      "available_read_tools": sorted(TOOLS & available),
                                      "login_verified": False},
                                error="Required upstream tools are missing." if missing else None,
                            )
                        phase = "calling the upstream tool"
                        result = await client.call_tool(name, arguments or {})
                        return LinkedInResult(
                            status="upstream_error" if result.is_error else "ok",
                            data=result.structured_content,
                            content=[block.model_dump(mode="json", by_alias=True, exclude_none=True)
                                     for block in result.content],
                            error="LinkedIn MCP returned a tool error; inspect content." if result.is_error else None,
                        )
        except TimeoutError:
            return LinkedInResult(status="timeout", error=f"Timed out while {phase}. No automatic retry was made.")
        except Exception as error:
            # Upstream exception strings can contain browser state or credentials.
            return LinkedInResult(status="network_error", error=(
                f"Failed while {phase} ({type(error).__name__}). "
                "Check the local LinkedIn MCP process and its stderr logs."))


def search_data(result: LinkedInResult) -> dict | None:
    if result.data is not None:
        return result.data
    for block in result.content:
        if block.get("type") == "text":
            try:
                data = json.loads(block["text"])
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
            if isinstance(data, dict):
                return data
    return None
