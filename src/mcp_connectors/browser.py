"""Lazy Chromium lifecycle; fresh, isolated contexts for each operation."""
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass

from playwright.async_api import Browser, Page, Error as PlaywrightError, async_playwright

from .config import Settings
from .errors import ConnectorError
from .parsing import inspect_page
from .security import validate_url
from .network import NetworkGuard


@dataclass(frozen=True)
class PageSnapshot:
    url: str
    html: str
    status: int = 200


class BrowserRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._stack = AsyncExitStack()
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()

    @property
    def started(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    async def _start(self) -> Browser:
        if self.started:
            assert self._browser is not None
            return self._browser
        await self._stack.aclose()
        try:
            playwright = await self._stack.enter_async_context(async_playwright())
            self._browser = await playwright.chromium.launch(
                headless=self.settings.headless,
                timeout=self.settings.timeout_ms,
            )
            self._stack.push_async_callback(self._browser.close)
            return self._browser
        except BaseException:
            self._browser = None
            await self._stack.aclose()
            raise

    @asynccontextmanager
    async def page(self, *, offline: bool = False) -> AsyncIterator[Page]:
        # One in-flight browser operation keeps site load and memory bounded.
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

    async def fetch(self, url: str, hosts: frozenset[str]) -> PageSnapshot:
        url = validate_url(url, hosts)
        # One retry only for network failures; challenges are never retried or solved.
        for attempt in range(2):
            try:
                async with asyncio.timeout(self.settings.timeout_ms / 1000 + 5):
                    async with self.page() as page:
                        session = await page.context.new_cdp_session(page)
                        tree = await session.send("Page.getFrameTree")
                        guard = NetworkGuard(session, tree["frameTree"]["frame"]["id"], hosts)
                        session.on("Fetch.requestPaused", guard.paused)
                        await session.send("Fetch.enable", {"patterns": [{"urlPattern": "*", "requestStage": "Request"}]})
                        try:
                            response = await page.goto(url, wait_until="domcontentloaded")
                            await page.wait_for_timeout(800)
                            if guard.errors:
                                raise guard.errors[0]
                            final_url = validate_url(page.url, hosts)
                            html = await page.content()
                            status = response.status if response else 200
                            inspect_page(html, status, final_url)
                            if len(html) > 8_000_000:
                                raise ConnectorError("layout_changed", "Page exceeded the 8 MB DOM limit", final_url)
                            return PageSnapshot(final_url, html, status)
                        except PlaywrightError as error:
                            if guard.errors:
                                raise guard.errors[0] from error
                            if not page.is_closed():
                                inspect_page(await page.content(), url=page.url)
                            raise ConnectorError("network_error", str(error).split("Call log:")[0].strip()[:400], url) from error
            except TimeoutError:
                failure = ConnectorError("network_error", "Browser operation timed out (including queue wait)", url)
            except PlaywrightError as error:
                failure = ConnectorError("network_error", str(error).split("Call log:")[0].strip()[:400], url)
            except ConnectorError as error:
                failure = error
                if error.detail.code != "network_error":
                    raise
            if attempt == 0:
                await asyncio.sleep(0.5)
        raise failure

    async def check(self) -> dict[str, str | bool]:
        async with self.page(offline=True) as page:
            await page.set_content(
                '<div id="status">pending</div>'
                '<script>document.querySelector("#status").textContent="rendered"</script>'
            )
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
