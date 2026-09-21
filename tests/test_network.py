import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from mcp_connectors.browser import BrowserRuntime
from mcp_connectors.config import Settings
from mcp_connectors.errors import ConnectorError
from mcp_connectors.network import NetworkGuard
from mcp_connectors.security import public_host


class NetworkTests(IsolatedAsyncioTestCase):
    async def test_private_dns_and_mixed_answers_fail_closed(self):
        loop = asyncio.get_running_loop()
        for addresses in (("127.0.0.1",), ("93.184.216.34", "10.0.0.2"), ("::1",)):
            records = [(0, 0, 0, "", (address, 443)) for address in addresses]
            with patch.object(loop, "getaddrinfo", AsyncMock(return_value=records)):
                with self.assertRaises(ConnectorError) as caught:
                    await public_host("www.cvbankas.lt")
                self.assertEqual(caught.exception.detail.code, "invalid_url")

    async def test_subresource_private_address_and_foreign_frame_are_aborted(self):
        session = AsyncMock()
        guard = NetworkGuard(session, "main", frozenset({"www.cvbankas.lt"}))
        for resource, frame, url in (("XHR", "main", "http://127.0.0.1/private"),
                                     ("Document", "child", "https://example.com/")):
            await guard.paused({"requestId": "1", "resourceType": resource, "frameId": frame, "request": {"url": url}})
            self.assertEqual(session.send.call_args.args[0], "Fetch.failRequest")

    async def test_navigation_limit(self):
        session = AsyncMock()
        guard = NetworkGuard(session, "main", frozenset({"www.cvbankas.lt"}))
        with patch("mcp_connectors.network.public_host", AsyncMock()):
            for i in range(9):
                await guard.paused({"requestId": str(i), "resourceType": "Document", "frameId": "main",
                                    "request": {"url": "https://www.cvbankas.lt/"}})
        self.assertEqual(guard.errors[-1].detail.code, "network_error")
        self.assertEqual(session.send.call_args.args[0], "Fetch.failRequest")

    async def test_challenge_frame_is_allowed_only_on_public_provider(self):
        session = AsyncMock()
        guard = NetworkGuard(session, "main", frozenset({"www.cvbankas.lt"}))
        with patch("mcp_connectors.network.public_host", AsyncMock()) as dns:
            await guard.paused({"requestId": "frame", "resourceType": "Document", "frameId": "child",
                                "request": {"url": "https://challenges.cloudflare.com/check"}})
            dns.assert_awaited_once_with("challenges.cloudflare.com")
            self.assertEqual(session.send.call_args.args[0], "Fetch.continueRequest")
        with patch("mcp_connectors.network.public_host", AsyncMock(side_effect=ConnectorError("invalid_url", "Private DNS"))):
            guard.reset()
            await guard.paused({"requestId": "frame", "resourceType": "Document", "frameId": "child",
                                "request": {"url": "https://challenges.cloudflare.com/check"}})
            self.assertEqual(session.send.call_args.args[0], "Fetch.failRequest")

    async def test_chromium_redirect_is_rejected_before_following(self):
        """Fulfill the initial HTTPS request locally; inspect a real Chromium redirect."""
        commands = []

        class RedirectSession:
            def __init__(self, session):
                self.session = session

            async def send(self, method, params):
                commands.append(method)
                if method == "Fetch.continueRequest":
                    return await self.session.send("Fetch.fulfillRequest", {
                        "requestId": params["requestId"], "responseCode": 302,
                        "responseHeaders": [{"name": "Location", "value": "http://127.0.0.1/private"}],
                    })
                return await self.session.send(method, params)

        class RedirectGuard(NetworkGuard):
            def __init__(self, session, main_frame, hosts):
                super().__init__(RedirectSession(session), main_frame, hosts)

        browser = BrowserRuntime(Settings(headless=True, timeout_ms=5000))
        try:
            with patch("mcp_connectors.browser.NetworkGuard", RedirectGuard), patch("mcp_connectors.network.public_host", AsyncMock()):
                with self.assertRaises(ConnectorError) as caught:
                    await browser.fetch("https://www.cvbankas.lt/start", frozenset({"www.cvbankas.lt"}))
            self.assertEqual(caught.exception.detail.code, "invalid_url")
            self.assertEqual(commands.count("Fetch.continueRequest"), 1)
            self.assertIn("Fetch.failRequest", commands)
        finally:
            await browser.close()
