"""Visible Chromium sessions with a dedicated profile and guarded source tabs."""
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass
import logging

from bs4 import BeautifulSoup
from playwright.async_api import Browser, BrowserContext, Page, Error as PlaywrightError, async_playwright

from .config import Settings
from .errors import ConnectorError
from .parsing import inspect_page, verification_required
from .security import validate_url
from .network import NetworkGuard

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PageSnapshot:
    url: str
    html: str
    status: int = 200


@dataclass
class SourceTab:
    page: Page
    guard: NetworkGuard
    status: int = 200
    requested_url: str | None = None
    waiting: bool = False

    def response(self, response):
        if response.request.is_navigation_request() and response.frame == self.page.main_frame:
            self.status = response.status


class BrowserRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._stack = AsyncExitStack()
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._tabs: dict[frozenset[str], SourceTab] = {}
        self._lock = asyncio.Lock()

    @property
    def started(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    @property
    def pending_verification(self) -> list[str]:
        return [tab.requested_url for tab in self._tabs.values()
                if tab.waiting and not tab.page.is_closed() and tab.requested_url]

    async def _start(self) -> Browser:
        if self.started:
            return self._browser
        await self._stack.aclose()
        self._tabs.clear()
        self._context = None
        try:
            playwright = await self._stack.enter_async_context(async_playwright())
            if self.settings.headless:
                self._browser = await playwright.chromium.launch(headless=True, timeout=self.settings.timeout_ms)
                self._stack.push_async_callback(self._browser.close)
            else:
                self.settings.profile_dir.mkdir(parents=True, exist_ok=True)
                self._context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=str(self.settings.profile_dir), headless=False,
                    channel="chrome" if self.settings.browser_channel == "chrome" else None,
                    locale=self.settings.locale, service_workers="block", accept_downloads=False,
                    timeout=self.settings.timeout_ms,
                )
                self._stack.push_async_callback(self._context.close)
                self._browser = self._context.browser
                self._context.set_default_timeout(self.settings.timeout_ms)
                self._context.set_default_navigation_timeout(self.settings.timeout_ms)
                # Startup tabs are not source tabs; no personal profile is imported.
                startup_pages = self._context.pages
                await self._context.new_page()
                for page in startup_pages:
                    await page.close()
            return self._browser
        except BaseException:
            self._browser = None
            self._context = None
            await self._stack.aclose()
            raise

    @asynccontextmanager
    async def page(self, *, offline: bool = False) -> AsyncIterator[Page]:
        """An isolated temporary page for headless fetches and offline diagnostics."""
        async with self._lock:
            browser = await self._start()
            context = await browser.new_context(locale=self.settings.locale, offline=offline,
                                                service_workers="block", accept_downloads=False)
            try:
                context.set_default_timeout(self.settings.timeout_ms)
                context.set_default_navigation_timeout(self.settings.timeout_ms)
                yield await context.new_page()
            finally:
                await context.close()

    async def _create_tab(self, page: Page, hosts: frozenset[str]) -> SourceTab:
        session = await page.context.new_cdp_session(page)
        tree = await session.send("Page.getFrameTree")
        guard = NetworkGuard(session, tree["frameTree"]["frame"]["id"], hosts)
        tab = SourceTab(page, guard)
        session.on("Fetch.requestPaused", guard.paused)
        page.on("response", tab.response)
        await session.send("Fetch.enable", {"patterns": [{"urlPattern": "*", "requestStage": "Request"}]})
        return tab

    @asynccontextmanager
    async def _source_tab(self, hosts: frozenset[str]) -> AsyncIterator[SourceTab]:
        if self.settings.headless:
            async with self.page() as page:
                yield await self._create_tab(page, hosts)
            return
        async with self._lock:
            await self._start()
            tab = self._tabs.get(hosts)
            if tab is None or tab.page.is_closed():
                available = [page for page in self._context.pages if page.url == "about:blank"
                             and all(page != existing.page for existing in self._tabs.values())]
                page = available[0] if available else await self._context.new_page()
                tab = await self._create_tab(page, hosts)
                self._tabs[hosts] = tab
            tab.guard.reset()
            await tab.page.bring_to_front()
            yield tab

    async def _snapshot(self, tab: SourceTab) -> PageSnapshot:
        if tab.guard.errors:
            raise tab.guard.errors[0]
        url = validate_url(tab.page.url, tab.guard.hosts)
        html = await tab.page.content()
        if len(html) > 8_000_000:
            raise ConnectorError("layout_changed", "Page exceeded the 8 MB DOM limit", url)
        inspect_page(html, tab.status, url)
        return PageSnapshot(url, html, tab.status)

    async def _read_or_wait(self, tab: SourceTab, *, wait: bool = True) -> PageSnapshot:
        try:
            result = await self._snapshot(tab)
        except ConnectorError as error:
            if error.detail.code != "blocked" or self.settings.headless:
                raise
            html = await tab.page.content()
            if not verification_required(BeautifulSoup(html, "html.parser")):
                raise
            tab.waiting = True
            if not wait:
                raise ConnectorError("blocked", "Verification is still pending in the open browser tab. Complete it before retrying.",
                                     tab.requested_url, tab.status)
            logger.warning("Complete the website verification in the visible Chromium tab: %s", tab.requested_url)
            deadline = asyncio.get_running_loop().time() + self.settings.verification_timeout_s
            while asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(1)
                try:
                    result = await self._snapshot(tab)
                    break
                except ConnectorError as pending:
                    if pending.detail.code != "blocked":
                        raise
                except PlaywrightError:
                    if tab.page.is_closed():
                        raise ConnectorError("blocked", "Verification tab was closed; retry to reopen it", tab.requested_url)
            else:
                raise ConnectorError("blocked", "Complete verification in the open Chromium tab, then retry this tool. The tab and session were kept open.",
                                     tab.requested_url, tab.status)
        tab.waiting = False
        return result

    async def fetch(self, url: str, hosts: frozenset[str]) -> PageSnapshot:
        url = validate_url(url, hosts)
        manual_wait = 0 if self.settings.headless else self.settings.verification_timeout_s
        for attempt in range(2):
            tab = None
            try:
                async with asyncio.timeout(self.settings.timeout_ms / 1000 + manual_wait + 5):
                    async with self._source_tab(hosts) as tab:
                        try:
                            if tab.waiting:
                                # Read a completed check before navigating; never discard a pending challenge.
                                previous = await self._read_or_wait(tab, wait=False)
                                if tab.requested_url == url:
                                    return previous
                            tab.requested_url = url
                            tab.status = 200
                            await tab.page.goto(url, wait_until="domcontentloaded")
                            await tab.page.wait_for_timeout(800)
                            return await self._read_or_wait(tab)
                        except PlaywrightError as error:
                            if tab.guard.errors:
                                raise tab.guard.errors[0] from error
                            if not tab.page.is_closed():
                                try:
                                    inspect_page(await tab.page.content(), tab.status, tab.page.url)
                                except ConnectorError as blocked:
                                    if blocked.detail.code == "blocked":
                                        return await self._read_or_wait(tab)
                                    raise
                            raise ConnectorError("network_error", str(error).split("Call log:")[0].strip()[:400], url) from error
            except TimeoutError:
                if tab is not None and tab.waiting:
                    raise ConnectorError("blocked", "Verification wait expired; complete the check in the open tab and retry", tab.requested_url, tab.status)
                failure = ConnectorError("network_error", "Browser operation timed out (including queue wait)", url)
            except PlaywrightError as error:
                message = str(error).split("Call log:")[0].strip()[:400]
                if not self.settings.headless and not self.started:
                    message = ("Cannot start the dedicated browser session. Ensure Google Chrome is installed "
                               "(or set MCP_BROWSER_CHANNEL=chromium), and close other connector processes using this profile. " + message)
                failure = ConnectorError("network_error", message, url)
            except ConnectorError as error:
                failure = error
                if error.detail.code != "network_error":
                    raise
            if not self.settings.headless and tab is not None and tab.page.is_closed():
                raise failure
            if attempt == 0:
                await asyncio.sleep(0.5)
        raise failure

    async def check(self) -> dict[str, str | bool]:
        async with self.page(offline=True) as page:
            await page.set_content('<div id="status">pending</div>'
                                   '<script>document.querySelector("#status").textContent="rendered"</script>')
            rendered = await page.locator("#status").inner_text()
            if rendered != "rendered":
                raise RuntimeError("Chromium did not execute the smoke-test JavaScript")
            return {"status": "ok", "headless": self.settings.headless, "javascript": rendered}

    async def close(self) -> None:
        async with self._lock:
            try:
                await self._stack.aclose()
            finally:
                self._browser = None
                self._context = None
                self._tabs.clear()
