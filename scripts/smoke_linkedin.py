"""Check the real optional backend through the main stdio MCP server."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

from mcp import Client, StdioServerParameters

from mcp_connectors.linkedin import LinkedInSettings
from smoke import unpack


def upstream_data(result):
    if result["data"] is not None:
        return result["data"]
    for block in result["content"]:
        if block["type"] == "text":
            try:
                return json.loads(block["text"])
            except json.JSONDecodeError:
                continue
    raise RuntimeError("Upstream did not return JSON data")


async def check(args):
    settings = LinkedInSettings(args.backend_url)
    target = StdioServerParameters(
        command=sys.executable, args=["-m", "mcp_connectors"],
        cwd=str(Path(__file__).resolve().parents[1]),
        env={"MCP_LINKEDIN_URL": settings.url},
    )
    async with asyncio.timeout(480):
        async with Client(target, read_timeout_seconds=230) as client:
            status = unpack(await client.call_tool("linkedin_status", {}))
            if status["status"] != "ok":
                raise RuntimeError(json.dumps(status))
            if not args.live:
                print(json.dumps({"status": "ok", "backend": status["data"], "live_tested": False}))
                return
            search = unpack(await client.call_tool("linkedin_search_jobs", {
                "options": {"keywords": args.keywords, "location": args.location, "max_pages": 1},
            }))
            if search["status"] != "ok":
                raise RuntimeError(json.dumps(search))
            data = upstream_data(search)
            job_ids = data.get("job_ids", [])
            if not job_ids:
                raise RuntimeError("Live search returned no job IDs; inspect login and upstream section_errors: "
                                   + json.dumps(data.get("section_errors", {})))
            detail = unpack(await client.call_tool("linkedin_get_job_details", {"job_id": job_ids[0]}))
            if detail["status"] != "ok":
                raise RuntimeError(json.dumps(detail))
            detail_data = upstream_data(detail)
            if not detail_data.get("sections") or detail_data.get("section_errors"):
                raise RuntimeError("Live detail has missing or failed sections: "
                                   + json.dumps(detail_data.get("section_errors", {})))
            if data.get("section_errors"):
                raise RuntimeError("Live search returned partial data: " + json.dumps(data["section_errors"]))
            print(json.dumps({"status": "ok", "live_tested": True, "job_count": len(job_ids),
                              "detail_sections": sorted(detail_data["sections"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-url", default="http://127.0.0.1:8001/mcp")
    parser.add_argument("--live", action="store_true", help="Open LinkedIn if needed; requires manual login")
    parser.add_argument("--keywords", default="python")
    parser.add_argument("--location", default="Vilnius, Lithuania")
    asyncio.run(check(parser.parse_args()))
