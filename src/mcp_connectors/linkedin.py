"""Read-only bridge to the optional, independently managed LinkedIn MCP server."""
import asyncio
from dataclasses import dataclass
import os
import re
from typing import Any, Literal
from urllib.parse import urlsplit

from mcp import Client
from pydantic import Field

from .models import Model


TOOLS = frozenset({"search_jobs", "get_job_details", "get_person_profile",
                   "get_company_profile"})


class LinkedInJobSearch(Model):
    keywords: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    max_pages: int = Field(default=1, ge=1, le=3, strict=True)
    date_posted: Literal["past_hour", "past_24_hours", "past_week", "past_month"] | None = None
    job_type: Literal["full_time", "part_time", "contract", "temporary", "volunteer", "internship", "other"] | None = None
    experience_level: Literal["internship", "entry", "associate", "mid_senior", "director", "executive"] | None = None
    work_type: Literal["on_site", "remote", "hybrid"] | None = None
    easy_apply: bool = False
    sort_by: Literal["relevance", "date"] | None = None


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
    status: Literal["ok", "disabled", "upstream_error", "network_error", "timeout"]
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
            "tools": ["linkedin_status"] + ["linkedin_" + name for name in sorted(TOOLS)],
        }

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
