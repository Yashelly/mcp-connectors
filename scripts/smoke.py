"""Real MCP client check; --http-url tests an already running HTTP server."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

from mcp import Client, StdioServerParameters

EXPECTED = {"cvbankas", "cvonline", "autogidas", "cvmarket", "autoplius"}


def unpack(result):
    if result.is_error:
        raise RuntimeError(str(result.content))
    if result.structured_content is not None:
        data = result.structured_content
        return data.get("result", data)
    return json.loads(result.content[0].text)


async def check(http_url: str | None) -> None:
    target = http_url or StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_connectors"],
        cwd=str(Path(__file__).resolve().parents[1]),
        env={"MCP_HEADLESS": "true"},
    )
    async with asyncio.timeout(60):
        async with Client(target, read_timeout_seconds=45) as client:
            names = {tool.name for tool in (await client.list_tools()).tools}
            assert names == {"health", "list_connectors", "browser_check"}, names
            status = unpack(await client.call_tool("health", {}))
            assert status["status"] == "ok" and status["headless"] is True, status
            if not http_url:
                assert status["browser_started"] is False, status
            adapters = unpack(await client.call_tool("list_connectors", {}))
            assert {item["id"] for item in adapters} == EXPECTED, adapters
            assert all(item["status"] == "planned" for item in adapters), adapters
            browser = unpack(await client.call_tool("browser_check", {}))
            assert browser == {"status": "ok", "headless": True, "javascript": "rendered"}, browser
            status = unpack(await client.call_tool("health", {}))
            assert status["browser_started"] is True, status
    print(json.dumps({"transport": "http" if http_url else "stdio", "status": "ok",
                      "connectors": sorted(EXPECTED), "browser": browser}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--http-url")
    asyncio.run(check(parser.parse_args().http_url))
