import unittest
import json
from pathlib import Path
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

from pydantic import ValidationError

from mcp_connectors.browser import BrowserRuntime, PageSnapshot
from mcp_connectors.config import Settings
from mcp_connectors.connectors import create_connectors
from mcp_connectors.errors import ConnectorError
from mcp_connectors.models import CarSearch, JobSearch
from mcp_connectors.parsing import inspect_page, salary
from mcp_connectors.security import validate_url

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(source, kind):
    return (FIXTURES / f"{source}_{kind}.html").read_text(encoding="utf-8")


class ParsingTests(unittest.TestCase):
    def setUp(self):
        self.adapters = create_connectors(BrowserRuntime(Settings()))

    def test_search_and_details_for_each_source(self):
        for source, adapter in self.adapters.items():
            with self.subTest(source=source):
                page = adapter.parse_search(fixture(source, "search"), adapter.info.website, 1)
                self.assertEqual(len(page.items), 2)
                self.assertTrue(page.has_more)
                self.assertEqual(page.items[0].source, source)
                detail = adapter.parse_listing(fixture(source, "listing"), page.items[0].url)
                self.assertEqual(detail.url, page.items[0].url)
                self.assertIsNotNone(detail.description)
                self.assertIsNotNone(detail.location)
                if detail.kind == "job":
                    self.assertEqual(detail.company, "Example Company")
                    self.assertEqual(detail.salary.currency, "EUR")
                    self.assertEqual(detail.salary.period, "MONTH")
                    self.assertIn("Python experience.", detail.requirements)
                    self.assertIsNotNone(detail.date_posted)
                else:
                    self.assertGreater(detail.price, 10000)
                    self.assertEqual(detail.currency, "EUR")
                    self.assertGreater(detail.mileage_km, 100000)
                    self.assertEqual(detail.transmission, "Automatinė")
                    self.assertIsNotNone(detail.make)
                    self.assertIsNotNone(detail.model)

    def test_real_empty_markers_are_required(self):
        for source, adapter in self.adapters.items():
            with self.subTest(source=source):
                result = adapter.parse_search(fixture(source, "empty"), adapter.info.website, 1)
                self.assertEqual(result.items, [])
                self.assertFalse(result.has_more)
                with self.assertRaises(ConnectorError) as caught:
                    adapter.parse_search("<html><h1>Unexpected layout</h1></html>", adapter.info.website, 1)
                self.assertEqual(caught.exception.detail.code, "layout_changed")

    def test_blocked_cannot_become_empty_or_a_listing(self):
        blocked = (FIXTURES / "blocked.html").read_text(encoding="utf-8")
        for adapter in self.adapters.values():
            for parse in (lambda: adapter.parse_search(blocked, adapter.info.website, 1),
                          lambda: adapter.parse_listing(blocked, adapter.info.website)):
                with self.assertRaises(ConnectorError) as caught:
                    parse()
                self.assertEqual(caught.exception.detail.code, "blocked")
        for status in (401, 403, 429):
            with self.assertRaises(ConnectorError) as caught:
                inspect_page("<html>Denied</html>", status)
            self.assertEqual(caught.exception.detail.code, "blocked")

    def test_normal_page_with_captcha_script_is_not_blocked(self):
        inspect_page('<html><script src="captcha.js"></script><p>Public listing</p></html>')

    def test_http_errors_are_not_empty(self):
        for status, expected in ((404, "not_found"), (410, "not_found"), (500, "network_error")):
            with self.assertRaises(ConnectorError) as caught:
                inspect_page("<html>Error</html>", status)
            self.assertEqual(caught.exception.detail.code, expected)

    def test_salary_decimal_range_and_missing_period(self):
        self.assertEqual(salary("8,06-14,85 €/val.").minimum, 8.06)
        self.assertEqual(salary("8,06-14,85 €/val.").period, "HOUR")
        self.assertIsNone(salary("Nuo 1 500 EUR").maximum)
        self.assertEqual(salary("Nuo 1 500 EUR").minimum, 1500)
        self.assertIsNone(salary("1500 EUR").period)
        self.assertIsNone(salary(None))

    def test_absent_values_stay_null(self):
        for source, adapter in self.adapters.items():
            item = adapter.parse_search(fixture(source, "search"), adapter.info.website, 1).items[1]
            self.assertIsNone(item.description)
            if item.kind == "job":
                self.assertIsNone(item.salary)
            else:
                self.assertIsNone(item.mileage_km)
                self.assertIsNone(item.fuel)

    def test_loan_and_export_prices_do_not_replace_sale_price(self):
        plus = self.adapters["autoplius"]
        self.assertEqual(plus.parse_search(fixture("autoplius", "search"), plus.info.website, 1).items[0].price, 3450)
        self.assertEqual(plus.parse_listing(fixture("autoplius", "listing"), "https://autoplius.lt/skelbimai/example-90000001.html").price, 25500)

    def test_missing_car_location_does_not_become_fuel(self):
        adapter = self.adapters["autoplius"]
        soup = adapter.soup(fixture("autoplius", "search"))
        for value in soup.select(".announcement-parameters-block span")[1:]:
            value.decompose()
        item = adapter.parse_search(str(soup), adapter.info.website, 1).items[0]
        self.assertIsNotNone(item.fuel)
        self.assertIsNone(item.location)

    def test_autogidas_sponsored_banner_is_not_a_car_card(self):
        adapter = self.adapters["autogidas"]
        html = fixture("autogidas", "search")
        banner = '<a class="item-link" rel="sponsored" href="https://r.autogidas.lt/trackers?id=example"><div class="lenders-content-title">Example finance banner</div></a>'
        result = adapter.parse_search(html.replace("</body>", banner + "</body>"), adapter.info.website, 1)
        self.assertEqual(len(result.items), 2)
        with self.assertRaises(ConnectorError) as caught:
            adapter.parse_search('<a class="item-link" href="/skelbimas/example-123.html"></a>', adapter.info.website, 1)
        self.assertEqual(caught.exception.detail.code, "layout_changed")

    def test_verified_url_filters_and_pagination(self):
        expected = {"cvbankas": ("keyw", "page", "2"), "cvmarket": ("search[keyword]", "start", "30"),
                    "cvonline": ("keywords[0]", "offset", "20"), "autogidas": ("f_376", "page", "2"),
                    "autoplius": ("qt", "page_nr", "2")}
        for source, adapter in self.adapters.items():
            options = JobSearch(query="a & b") if adapter.info.category == "jobs" else CarSearch(query="a & b", year_from=2015, price_to=20000)
            query = parse_qs(urlsplit(adapter.search_url(options, 2)).query)
            keyword, page_key, page_value = expected[source]
            self.assertEqual(query[keyword], ["a & b"])
            self.assertEqual(query[page_key], [page_value])

    def test_cvmarket_first_page_preserves_filters_without_redirect(self):
        url = self.adapters["cvmarket"].search_url(JobSearch(query="python", city="Vilnius"), 1)
        params = parse_qs(urlsplit(url).query)
        self.assertNotIn("start", params)
        self.assertEqual(params["search[locations][]"], ["134"])

    def test_city_filters_use_observed_site_ids(self):
        for source, key, value in (("cvbankas", "location[]", "606"), ("cvmarket", "search[locations][]", "134"),
                                    ("cvonline", "towns[0]", "540")):
            params = parse_qs(urlsplit(self.adapters[source].search_url(JobSearch(city="Vilnius"), 1)).query)
            self.assertEqual(params[key], [value])

    def test_cvonline_location_dictionary_and_list_formats(self):
        adapter = self.adapters["cvonline"]
        for towns in ({"540": {"id": 540, "name": "Vilnius"}}, [{"id": 540, "name": "Vilnius"}]):
            soup = adapter.soup(fixture("cvonline", "search"))
            payload = json.loads(soup.select_one("#__NEXT_DATA__").string)
            payload["props"]["pageProps"]["initialState"]["locations"]["towns"] = towns
            soup.select_one("#__NEXT_DATA__").string = json.dumps(payload)
            result = adapter.parse_search(str(soup), adapter.info.website, 1)
            self.assertEqual(result.items[0].location, "Vilnius, Lithuania")


class ValidationTests(unittest.TestCase):
    def test_bounds_and_unknown_filters(self):
        for values in ({"limit": 0}, {"limit": 51}, {"max_pages": 4}, {"page": 0},
                       {"query": "x" * 201}, {"limit": True}, {"unknown": "x"}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                JobSearch(**values)
        with self.assertRaises(ValidationError):
            CarSearch(price_from=20000, price_to=10000)
        with self.assertRaises(ValidationError):
            CarSearch(year_from=2025, year_to=2015)

    def test_url_boundary(self):
        hosts = frozenset(("cvbankas.lt", "www.cvbankas.lt"))
        for url in ("file:///etc/passwd", "http://127.0.0.1", "http://[::1]", "https://localhost", "https://10.0.0.1", "https://169.254.169.254/latest",
                    "https://www.cvbankas.lt.evil.test/", "https://evil.cvbankas.lt/", "https://user@www.cvbankas.lt/",
                    "https://www.cvbankas.lt:444/", "https://www.cvbankas.lt\\@127.0.0.1/", " https://www.cvbankas.lt/", "https://www.cvbankas.lt\n/"):
            with self.subTest(url=url), self.assertRaises(ConnectorError):
                validate_url(url, hosts)
        self.assertEqual(validate_url("https://www.cvbankas.lt/path#fragment", hosts), "https://www.cvbankas.lt/path")


class PaginationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.browser = AsyncMock()
        self.adapter = create_connectors(self.browser)["cvbankas"]
        self.html = fixture("cvbankas", "search")

    async def test_limit_and_page_budget(self):
        self.browser.fetch.return_value = PageSnapshot("https://www.cvbankas.lt/", self.html)
        result = await self.adapter.search(JobSearch(limit=1, max_pages=3))
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.pages_fetched, 1)
        self.assertTrue(result.truncated)
        self.assertEqual(result.next_page, 1)
        self.assertEqual(self.browser.fetch.await_count, 1)

    async def test_two_pages_deduplicate_and_preserve_partial_failure(self):
        self.browser.fetch.side_effect = [PageSnapshot("https://www.cvbankas.lt/", self.html), ConnectorError("blocked", "Verification required")]
        result = await self.adapter.search(JobSearch(limit=10, max_pages=2))
        self.assertEqual(result.status, "partial")
        self.assertEqual(len(result.items), 2)
        self.assertEqual(result.errors[0].code, "blocked")

    async def test_duplicate_page_is_not_silent_success(self):
        self.browser.fetch.return_value = PageSnapshot("https://www.cvbankas.lt/", self.html)
        result = await self.adapter.search(JobSearch(limit=10, max_pages=3))
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.errors[0].code, "layout_changed")
        self.assertEqual(self.browser.fetch.await_count, 2)

    async def test_distinct_second_page(self):
        second = self.html.replace("9000001", "9000003").replace("9000002", "9000004").replace("page=2", "page=3")
        self.browser.fetch.side_effect = [PageSnapshot("https://www.cvbankas.lt/", self.html), PageSnapshot("https://www.cvbankas.lt/", second)]
        result = await self.adapter.search(JobSearch(limit=10, max_pages=2))
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.items), 4)
        self.assertEqual(result.next_page, 3)

    async def test_invalid_listing_url_never_fetches(self):
        for url in ("https://www.cvbankas.lt/", "https://www.cvbankas.lt/example/1-9000001?redirect=http://127.0.0.1"):
            self.assertEqual((await self.adapter.get_listing(url)).status, "invalid_url")
        self.browser.fetch.assert_not_called()

    async def test_malformed_card_becomes_source_error(self):
        self.browser.fetch.return_value = PageSnapshot("https://www.cvbankas.lt/", '<a class="list_a"><h3>Missing href</h3></a>')
        result = await self.adapter.search(JobSearch())
        self.assertEqual(result.status, "layout_changed")
