import argparse
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging

from mcp.server import MCPServer
from mcp.server.mcpserver import Context

from . import __version__
from .browser import BrowserRuntime
from .config import Settings
from .connectors import create_connectors
from .connectors.base import Connector


@dataclass
class AppState:
    browser: BrowserRuntime
    connectors: dict[str, Connector]


@asynccontextmanager
async def lifespan(server: MCPServer) -> AsyncIterator[AppState]:
    browser = BrowserRuntime(Settings.from_env())
    try:
        yield AppState(browser, create_connectors(browser))
    finally:
        await browser.close()


mcp = MCPServer(
    "mcp-connectors",
    version=__version__,
    instructions="Scaffold only. Website adapters are planned; search and listing tools are not implemented.",
    lifespan=lifespan,
)


@mcp.tool()
async def health(ctx: Context[AppState]) -> dict:
    """Report server health and configuration without launching a browser."""
    state = ctx.request_context.lifespan_context
    return {
        "status": "ok",
        "version": __version__,
        "headless": state.browser.settings.headless,
        "browser_started": state.browser.started,
        "connectors": len(state.connectors),
    }


@mcp.tool()
async def list_connectors(ctx: Context[AppState]) -> list[dict[str, str]]:
    """List website adapters and their actual implementation status."""
    return [adapter.describe() for adapter in ctx.request_context.lifespan_context.connectors.values()]


@mcp.tool()
async def browser_check(ctx: Context[AppState]) -> dict[str, str | bool]:
    """Launch Chromium and verify JavaScript offline; this does not access websites."""
    return await ctx.request_context.lifespan_context.browser.check()


def main() -> None:
    parser = argparse.ArgumentParser(description="Headless website MCP server")
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    logging.basicConfig(level=logging.INFO)
    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport="streamable-http", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
