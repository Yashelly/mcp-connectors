import base64
from pathlib import Path
import tempfile
import time
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from playwright.async_api import BrowserType

from mcp_connectors.browser import BrowserRuntime, PageSnapshot, SourceTab
from mcp_connectors.config import Settings
from mcp_connectors.errors import ConnectorError
from mcp_connectors.network import NetworkGuard

HOSTS = frozenset({"www.cvbankas.lt", "cvbankas.lt"})
URL = "https://www.cvbankas.lt/test"
CHALLENGE = "<html><title>Just a moment...</title><body>Verify you are human</body></html>"


class VerificationTests(IsolatedAsyncioTestCase):
    def tab(self):
        page = MagicMock()
        page.content = AsyncMock(return_value=CHALLENGE)
        page.is_closed.return_value = False
        return SourceTab(page, NetworkGuard(AsyncMock(), "main", HOSTS), 403, URL)

    async def test_completed_verification_returns_new_response_status(self):
        browser = BrowserRuntime(Settings())
        tab = self.tab()
        expected = PageSnapshot(URL, "<h1>Results</h1>", 200)
        browser._snapshot = AsyncMock(side_effect=[ConnectorError("blocked", "Verification", URL, 403), expected])
        with patch("mcp_connectors.browser.asyncio.sleep", AsyncMock()):
            self.assertEqual(await browser._read_or_wait(tab), expected)
        self.assertFalse(tab.waiting)
        tab.page.close.assert_not_called()

    async def test_wait_expiry_keeps_pending_tab(self):
        browser = BrowserRuntime(Settings(verification_timeout_s=0))
        tab = self.tab()
        browser._snapshot = AsyncMock(side_effect=ConnectorError("blocked", "Verification", URL, 403))
        browser._tabs[HOSTS] = tab
        with self.assertRaises(ConnectorError) as caught:
            await browser._read_or_wait(tab)
        self.assertEqual(caught.exception.detail.code, "blocked")
        self.assertEqual(browser.pending_verification, [URL])
        tab.page.close.assert_not_called()

    async def test_headless_and_plain_denial_do_not_wait(self):
        for headless, html in ((True, CHALLENGE), (False, "<h1>Access denied</h1>")):
            browser = BrowserRuntime(Settings(headless=headless))
            tab = self.tab()
            tab.page.content.return_value = html
            browser._snapshot = AsyncMock(side_effect=ConnectorError("blocked", "Denied", URL, 403))
            with self.assertRaises(ConnectorError):
                await browser._read_or_wait(tab)
            self.assertFalse(tab.waiting)

    async def test_retry_does_not_restart_an_unresolved_verification_wait(self):
        browser = BrowserRuntime(Settings())
        tab = self.tab()
        tab.waiting = True
        browser._snapshot = AsyncMock(side_effect=ConnectorError("blocked", "Verification", URL, 403))
        with patch("mcp_connectors.browser.asyncio.sleep", AsyncMock()) as sleep:
            with self.assertRaises(ConnectorError) as caught:
                await browser._read_or_wait(tab, wait=False)
            sleep.assert_not_awaited()
        self.assertEqual(caught.exception.detail.code, "blocked")


class PersistentProfileTests(IsolatedAsyncioTestCase):
    async def test_tab_reuse_profile_restart_and_closed_window_recovery(self):
        """Exercise real persistent Chromium with synthetic local responses only.

        The production visible launch is rendered headlessly inside this test,
        so unattended check.ps1 runs do not require an interactive desktop.
        """
        launch = BrowserType.launch_persistent_context
        launches = []

        async def test_launch(browser_type, *args, **kwargs):
            launches.append(kwargs["headless"])
            kwargs["headless"] = True
            kwargs["channel"] = None
            return await launch(browser_type, *args, **kwargs)

        class FixtureSession:
            def __init__(self, session):
                self.session = session

            async def send(self, method, params):
                if method == "Fetch.continueRequest":
                    return await self.session.send("Fetch.fulfillRequest", {
                        "requestId": params["requestId"], "responseCode": 200,
                        "responseHeaders": [{"name": "Content-Type", "value": "text/html"}],
                        "body": base64.b64encode(b"<html><h1>Local test page</h1></html>").decode(),
                    })
                return await self.session.send(method, params)

        class FixtureGuard(NetworkGuard):
            def __init__(self, session, main_frame, hosts):
                super().__init__(FixtureSession(session), main_frame, hosts)

        with tempfile.TemporaryDirectory() as directory, \
                patch.object(BrowserType, "launch_persistent_context", test_launch), \
                patch("mcp_connectors.browser.NetworkGuard", FixtureGuard), \
                patch("mcp_connectors.network.public_host", AsyncMock()):
            settings = Settings(profile_dir=Path(directory), timeout_ms=5000)
            browser = BrowserRuntime(settings)
            try:
                await browser.fetch(URL, HOSTS)
                page = browser._tabs[HOSTS].page
                await browser._context.add_cookies([{"name": "test_session", "value": "retained",
                    "domain": "www.cvbankas.lt", "path": "/", "expires": time.time() + 3600, "httpOnly": True}])
                await browser.fetch(URL + "-second", HOSTS)
                self.assertIs(browser._tabs[HOSTS].page, page)
                self.assertEqual(browser._tabs[HOSTS].guard.document_requests, 1)
                await page.close()
                await browser.fetch(URL, HOSTS)
                self.assertIsNot(browser._tabs[HOSTS].page, page)
                await browser.close()
                self.assertFalse(browser.started)

                restarted = BrowserRuntime(settings)
                try:
                    await restarted.fetch(URL, HOSTS)
                    cookies = await restarted._context.cookies(URL)
                    self.assertTrue(any(c["name"] == "test_session" and c["value"] == "retained" for c in cookies))
                finally:
                    await restarted.close()
            finally:
                await browser.close()
            self.assertTrue(launches)
            self.assertTrue(all(headless is False for headless in launches))
