import asyncio
import json
import unittest
from unittest.mock import AsyncMock, call, patch

from mcp import Client
from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent
from pydantic import ValidationError

from mcp_connectors.linkedin import LinkedInBridge, LinkedInJobSearch, LinkedInResult, LinkedInSettings
from mcp_connectors.server import mcp


class LinkedInSettingsTests(unittest.TestCase):
    def test_only_explicit_loopback_backend_is_accepted(self):
        for url in ("https://example.com/mcp", "http://localhost:8001/mcp",
                    "http://127.0.0.1/mcp", "http://127.0.0.1:8001/other",
                    "http://user:secret@127.0.0.1:8001/mcp", "http://127.0.0.1:8001/mcp?token=x",
                    "http://127.0.0.1:8001/mcp#x", "http://127.0.0.1:0/mcp"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                LinkedInSettings(url)
        self.assertEqual(LinkedInSettings("http://127.0.0.1:8001/mcp").timeout_s, 210)
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(LinkedInSettings.from_env().url)

    def test_search_bounds_and_upstream_filter_values(self):
        for options in ({"max_pages": 4}, {"max_pages": True}, {"keywords": ""},
                        {"sort_by": "recent"}, {"unexpected": True}):
            with self.subTest(options=options), self.assertRaises(ValidationError):
                LinkedInJobSearch.model_validate({"keywords": "python", **options})
        self.assertEqual(LinkedInJobSearch(keywords="python", sort_by="date").max_pages, 1)


class LinkedInBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_and_forbidden_tools_never_connect(self):
        bridge = LinkedInBridge(LinkedInSettings())
        with patch("mcp_connectors.linkedin.Client") as client:
            self.assertEqual((await bridge.call("status")).status, "disabled")
            for name in ("send_message", "connect_with_person", "close_session"):
                with self.assertRaises(ValueError):
                    await bridge.call(name)
            client.assert_not_called()

    async def test_real_mcp_preserves_data_errors_and_checks_compatibility(self):
        upstream = MCPServer("test-linkedin")

        @upstream.tool()
        async def search_jobs(keywords: str, location: str | None = None, max_pages: int = 1) -> dict:
            return {"job_ids": ["123"], "sections": {"jobs": "Example job"},
                    "section_errors": {"page_2": {"error_type": "timeout"}},
                    "received": [keywords, location, max_pages]}

        @upstream.tool()
        async def get_job_details(job_id: str) -> CallToolResult:
            return CallToolResult(is_error=True, content=[TextContent(type="text", text="Manual login required")])

        @upstream.tool()
        async def get_company_profile(company_name: str) -> CallToolResult:
            return CallToolResult(structured_content={"sections": {"about": company_name}},
                                  content=[TextContent(type="text", text="Original content")])

        bridge = LinkedInBridge(LinkedInSettings("http://127.0.0.1:8001/mcp"))
        with patch("mcp_connectors.linkedin.Client", side_effect=lambda *args, **kwargs: Client(upstream)):
            result = await bridge.call("search_jobs", {"keywords": "python", "location": "Vilnius", "max_pages": 2})
            self.assertEqual(result.status, "ok")
            data = result.data or json.loads(result.content[0]["text"])
            self.assertEqual(data["received"], ["python", "Vilnius", 2])
            self.assertIn("section_errors", data)
            self.assertTrue(result.content)
            failure = await bridge.call("get_job_details", {"job_id": "123"})
            self.assertEqual(failure.status, "upstream_error")
            self.assertEqual(failure.content[0]["text"], "Manual login required")
            company = await bridge.call("get_company_profile", {"company_name": "example"})
            self.assertEqual(company.data, {"sections": {"about": "example"}})
            self.assertEqual(company.content[0]["text"], "Original content")
            status = await bridge.call("status")
            self.assertEqual(status.status, "upstream_error")
            self.assertEqual(status.data["missing_tools"], ["get_person_profile"])
            self.assertFalse(status.data["login_verified"])

    async def test_public_tools_forward_exact_arguments_and_reject_invalid_input(self):
        with patch.dict("os.environ", {"MCP_LINKEDIN_URL": ""}), patch.object(
            LinkedInBridge, "call", new_callable=AsyncMock,
            return_value=LinkedInResult(status="ok", data={"sections": {"main": "Example"}}),
        ) as upstream:
            async with Client(mcp) as client:
                for name, arguments in (
                    ("linkedin_search_jobs", {"options": {"keywords": "python", "location": "Vilnius"}}),
                    ("linkedin_get_job_details", {"job_id": "123"}),
                    ("linkedin_get_person_profile", {"linkedin_username": "example", "sections": "experience", "max_scrolls": 2}),
                    ("linkedin_get_company_profile", {"company_name": "example", "sections": "jobs"}),
                    ("linkedin_status", {}),
                ):
                    result = await client.call_tool(name, arguments)
                    self.assertFalse(result.is_error, result)
                self.assertEqual(upstream.await_args_list, [
                    call("search_jobs", {"keywords": "python", "location": "Vilnius", "max_pages": 1, "easy_apply": False}),
                    call("get_job_details", {"job_id": "123"}),
                    call("get_person_profile", {"linkedin_username": "example", "sections": "experience", "max_scrolls": 2}),
                    call("get_company_profile", {"company_name": "example", "sections": "jobs"}),
                    call("status"),
                ])
                upstream.reset_mock()
                for name, arguments in (
                    ("linkedin_get_job_details", {"job_id": "http://127.0.0.1"}),
                    ("linkedin_get_person_profile", {"linkedin_username": "../other"}),
                    ("linkedin_get_company_profile", {"company_name": "https://example.com"}),
                    ("linkedin_search_jobs", {"options": {"keywords": "python", "max_pages": 4}}),
                ):
                    self.assertTrue((await client.call_tool(name, arguments)).is_error)
                upstream.assert_not_awaited()

    async def test_connection_failure_is_sanitized(self):
        bridge = LinkedInBridge(LinkedInSettings("http://127.0.0.1:8001/mcp"))
        with patch("mcp_connectors.linkedin.Client", side_effect=OSError("secret-cookie-value")):
            result = await bridge.call("search_jobs", {"keywords": "python"})
        self.assertEqual(result.status, "network_error")
        self.assertIn("connecting", result.error)
        self.assertNotIn("secret-cookie-value", result.model_dump_json())

    async def test_timeout_closes_client_without_retry(self):
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.call_tool.side_effect = TimeoutError
        bridge = LinkedInBridge(LinkedInSettings("http://127.0.0.1:8001/mcp"))
        with patch("mcp_connectors.linkedin.Client", return_value=client):
            result = await bridge.call("get_job_details", {"job_id": "123"})
        self.assertEqual(result.status, "timeout")
        client.call_tool.assert_awaited_once()
        client.__aexit__.assert_awaited_once()

    async def test_queue_wait_is_bounded_and_cancellation_propagates(self):
        bridge = LinkedInBridge(LinkedInSettings("http://127.0.0.1:8001/mcp", timeout_s=1))
        await bridge._lock.acquire()
        try:
            with patch("mcp_connectors.linkedin.Client") as client:
                result = await bridge.call("status")
                self.assertEqual(result.status, "timeout")
                self.assertIn("request slot", result.error)
                task = asyncio.create_task(bridge.call("status"))
                await asyncio.sleep(0)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                client.assert_not_called()
        finally:
            bridge._lock.release()


if __name__ == "__main__":
    unittest.main()
