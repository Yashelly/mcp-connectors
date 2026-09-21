"""Lazy Chromium lifecycle; fresh, isolated contexts for each operation."""
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from collections.abc import AsyncIterator

from playwright.async_api import Browser, Page, async_playwright

from .config import Settings


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
        # Serialize operations in the scaffold; real adapters can later add a bounded pool.
        async with self._lock:
            browser = await self._start()
            context = await browser.new_context(locale=self.settings.locale, offline=offline)
            try:
                context.set_default_timeout(self.settings.timeout_ms)
                context.set_default_navigation_timeout(self.settings.timeout_ms)
                yield await context.new_page()
            finally:
                await context.close()

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
