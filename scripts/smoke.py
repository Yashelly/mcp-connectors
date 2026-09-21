"""Real MCP client check; --http-url tests an already running HTTP server."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import socket
import subprocess
import os

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
            assert names == {"health", "list_connectors", "browser_check", "search_jobs", "search_cars", "get_listing"}, names
            status = unpack(await client.call_tool("health", {}))
            assert status["status"] == "ok" and status["headless"] is True, status
            if not http_url:
                assert status["browser_started"] is False, status
            adapters = unpack(await client.call_tool("list_connectors", {}))
            assert {item["id"] for item in adapters} == EXPECTED, adapters
            assert all(item["status"] == "implemented" for item in adapters), adapters
            rejected = unpack(await client.call_tool("get_listing", {"source": "cvbankas", "url": "http://127.0.0.1/private"}))
            assert rejected["status"] == "invalid_url", rejected
            invalid = await client.call_tool("search_jobs", {"options": {"limit": 51}})
            assert invalid.is_error, invalid
            empty_sources = unpack(await client.call_tool("search_cars", {"options": {}, "sources": []}))
            assert empty_sources["results"] == [], empty_sources
            browser = unpack(await client.call_tool("browser_check", {}))
            assert browser == {"status": "ok", "headless": True, "javascript": "rendered"}, browser
            status = unpack(await client.call_tool("health", {}))
            assert status["browser_started"] is True, status
    print(json.dumps({"transport": "http" if http_url else "stdio", "status": "ok",
                      "connectors": sorted(EXPECTED), "browser": browser}))


async def all_transports():
    await check(None)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    root = Path(__file__).resolve().parents[1]
    with subprocess.Popen([sys.executable, "-m", "mcp_connectors", "--transport", "streamable-http", "--port", str(port)],
                          cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          env={**os.environ, "MCP_HEADLESS": "true"},
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0) as process:
        try:
            for _ in range(50):
                if process.poll() is not None:
                    raise RuntimeError("HTTP server exited during startup")
                try:
                    reader, writer = await asyncio.open_connection("127.0.0.1", port)
                    writer.close()
                    await writer.wait_closed()
                    break
                except OSError:
                    await asyncio.sleep(0.2)
            else:
                raise RuntimeError("HTTP server did not start")
            await check(f"http://127.0.0.1:{port}/mcp")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--http-url")
    parser.add_argument("--all-transports", action="store_true")
    args = parser.parse_args()
    asyncio.run(all_transports() if args.all_transports else check(args.http_url))
