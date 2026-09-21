import unittest
from unittest.mock import patch

from mcp_connectors.browser import BrowserRuntime
from mcp_connectors.config import Settings
from mcp_connectors.connectors import create_connectors


class SettingsTests(unittest.TestCase):
    def test_headless_is_default(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertTrue(Settings.from_env().headless)

    def test_invalid_configuration_fails(self):
        for env in ({"MCP_HEADLESS": "maybe"}, {"MCP_BROWSER_TIMEOUT_MS": "0"}):
            with self.subTest(env=env), patch.dict("os.environ", env, clear=True):
                with self.assertRaises(ValueError):
                    Settings.from_env()


class ConnectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_registry_is_lazy_and_placeholders_fail_honestly(self):
        browser = BrowserRuntime(Settings())
        try:
            registry = create_connectors(browser)
            self.assertEqual(set(registry), {"cvbankas", "cvonline", "autogidas", "cvmarket", "autoplius"})
            self.assertFalse(browser.started)
            for adapter in registry.values():
                self.assertEqual(adapter.describe()["status"], "planned")
                with self.assertRaises(NotImplementedError):
                    await adapter.search("example")
                with self.assertRaises(NotImplementedError):
                    await adapter.get_listing(adapter.info.website)
            self.assertFalse(browser.started)
        finally:
            await browser.close()

    async def test_browser_recovers_after_operation_failure(self):
        browser = BrowserRuntime(Settings())
        try:
            with self.assertRaisesRegex(RuntimeError, "test failure"):
                async with browser.page(offline=True):
                    raise RuntimeError("test failure")
            result = await browser.check()
            self.assertEqual(result["javascript"], "rendered")
        finally:
            await browser.close()
        self.assertFalse(browser.started)


if __name__ == "__main__":
    unittest.main()
