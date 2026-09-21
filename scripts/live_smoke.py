"""Small real MCP live check. Blocking is recorded and produces a nonzero exit."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import os

from mcp import Client, StdioServerParameters
from smoke import unpack

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("cvbankas", "cvmarket", "cvonline", "autoplius", "autogidas")
CAR_DETAIL_URLS = {
    "autoplius": "https://autoplius.lt/skelbimai/bmw-330-2-0-l-sedanas-2020-benzinas-elektra-31644037.html",
    "autogidas": "https://autogidas.lt/skelbimas/cadillac-cts-2016-m-sedanas-0139917402.html",
}


async def run(args):
    target = args.http_url or StdioServerParameters(command=sys.executable, args=["-m", "mcp_connectors"],
                    cwd=str(ROOT), env={**os.environ, "MCP_HEADLESS": str(args.headless).lower()})
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "transport": "http" if args.http_url else "stdio", "sources": {}}
    async with Client(target, read_timeout_seconds=900) as client:
        health = unpack(await client.call_tool("health", {}))
        report["headless"] = health["headless"]
        report["browser_channel"] = health["browser_channel"]
        for source in args.sources:
            cars = source in CAR_DETAIL_URLS
            tool = "search_cars" if cars else "search_jobs"
            options = {"limit": 2, "max_pages": 1, "query": "" if cars else "python"}
            if cars:
                options.update(price_from=10000, price_to=20000, year_from=2015, year_to=2020)
            else:
                options["city"] = "Vilnius"
            result = unpack(await client.call_tool(tool, {"options": options, "sources": [source]}))["results"][0]
            print(json.dumps({"source": source, "stage": "search", "status": result["status"],
                              "count": len(result["items"]), "errors": result["errors"]}, ensure_ascii=True), flush=True)
            entry = {"search": {key: result[key] for key in ("status", "pages_fetched", "has_more", "truncated", "errors")},
                     "count": len(result["items"]), "options": options}
            url = result["items"][0]["url"] if result["items"] else CAR_DETAIL_URLS.get(source)
            if url:
                detail = unpack(await client.call_tool("get_listing", {"source": source, "url": url}))
                entry["detail"] = {"status": detail["status"], "url": url, "error": detail.get("error"),
                                   "populated_fields": [k for k, v in (detail.get("item") or {}).items() if v is not None]}
            else:
                entry["detail"] = {"status": "not_run", "reason": "Search returned no listing URL"}
            if args.extended and result["status"] == "ok":
                empty = unpack(await client.call_tool(tool, {"sources": [source], "options": {"query": "zzqxnomatch7319", "limit": 1}}))["results"][0]
                page_two = unpack(await client.call_tool(tool, {"sources": [source], "options": {"page": 2, "limit": 2}}))["results"][0]
                entry["empty_probe"] = {"status": empty["status"], "count": len(empty["items"])}
                entry["page_two"] = {"status": page_two["status"], "count": len(page_two["items"]), "urls": [i["url"] for i in page_two["items"]]}
            report["sources"][source] = entry
            print(json.dumps({"source": source, **entry}, ensure_ascii=True), flush=True)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if all(e["search"]["status"] == "ok" and e["detail"]["status"] == "ok"
                    and (not args.extended or e.get("empty_probe", {}).get("status") == "empty"
                         and e.get("page_two", {}).get("status") == "ok") for e in report["sources"].values()) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--http-url")
    parser.add_argument("--headless", action="store_true", help="Use isolated headless Chromium instead of the default visible persistent session")
    parser.add_argument("--sources", choices=SOURCES, nargs="+", default=list(SOURCES))
    parser.add_argument("--extended", action="store_true", help="Also probe empty results and page 2 for accessible sources")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "live-smoke.json")
    sys.exit(asyncio.run(run(parser.parse_args())))
