from dataclasses import asdict, dataclass
import re
from typing import Literal
from urllib.parse import urljoin, urlsplit

from ..browser import BrowserRuntime
from ..errors import ConnectorError
from ..models import CarSearch, JobSearch, Listing, ListingResult, SearchResult
from ..parsing import inspect_page
from ..security import validate_url


@dataclass(frozen=True)
class ConnectorInfo:
    id: str
    name: str
    website: str
    category: Literal["jobs", "cars"]
    status: str = "implemented"
    live_status: str = "unverified"
    last_live_check: str | None = None


@dataclass
class ParsedPage:
    items: list[Listing]
    has_more: bool


class Connector:
    info: ConnectorInfo
    listing_pattern: str
    filters: tuple[str, ...] = ("query",)

    def __init__(self, browser: BrowserRuntime) -> None:
        self.browser = browser
        domain = urlsplit(self.info.website).hostname.removeprefix("www.")
        self.hosts = frozenset((domain, "www." + domain))

    def describe(self) -> dict:
        return {**asdict(self.info), "filters": list(self.filters)}

    def listing_url(self, url: str, *, relative: bool = False) -> str:
        if relative:
            url = urljoin(self.info.website, url)
        url = validate_url(url, self.hosts)
        parts = urlsplit(url)
        if not re.fullmatch(self.listing_pattern, parts.path):
            raise ConnectorError("invalid_url", "URL is not a supported public listing path")
        if parts.query:
            raise ConnectorError("invalid_url", "Listing URLs must not contain query parameters")
        return url

    def search_url(self, options: JobSearch | CarSearch, page: int) -> str:
        raise NotImplementedError

    def parse_search(self, html: str, url: str, page: int) -> ParsedPage:
        raise NotImplementedError

    def parse_listing(self, html: str, url: str) -> Listing:
        raise NotImplementedError

    async def search(self, options: JobSearch | CarSearch) -> SearchResult:
        result = SearchResult(source=self.info.id, status="empty")
        seen: set[str] = set()
        for page in range(options.page, options.page + options.max_pages):
            try:
                url = self.search_url(options, page)
                snapshot = await self.browser.fetch(url, self.hosts)
                parsed = self.parse_search(snapshot.html, snapshot.url, page)
                result.pages_fetched += 1
                new = [item for item in parsed.items if item.url not in seen]
                if parsed.items and not new and result.items:
                    raise ConnectorError("layout_changed", "Pagination returned only previously seen listings", url)
                for item in new:
                    if item.url in seen:
                        continue
                    self.listing_url(item.url)
                    seen.add(item.url)
                    if len(result.items) < options.limit:
                        result.items.append(item)
                    else:
                        result.truncated = True
                result.has_more = parsed.has_more or result.truncated
                result.next_page = page if result.truncated else page + 1 if parsed.has_more else None
                if len(result.items) >= options.limit or not parsed.has_more:
                    break
            except ConnectorError as error:
                result.errors.append(error.detail)
                result.status = "partial" if result.items else error.detail.code
                return result
            except (KeyError, TypeError, ValueError, AttributeError, IndexError) as error:
                result.errors.append(ConnectorError("layout_changed", f"Unexpected source data: {type(error).__name__}", url).detail)
                result.status = "partial" if result.items else "layout_changed"
                return result
        result.status = "ok" if result.items else "empty"
        return result

    async def get_listing(self, url: str) -> ListingResult:
        try:
            url = self.listing_url(url)
            snapshot = await self.browser.fetch(url, self.hosts)
            final_url = self.listing_url(snapshot.url)
            item = self.parse_listing(snapshot.html, final_url)
            return ListingResult(source=self.info.id, status="ok", item=item)
        except ConnectorError as error:
            return ListingResult(source=self.info.id, status=error.detail.code, error=error.detail)
        except (KeyError, TypeError, ValueError, AttributeError, IndexError) as error:
            failure = ConnectorError("layout_changed", f"Unexpected source data: {type(error).__name__}", url)
            return ListingResult(source=self.info.id, status="layout_changed", error=failure.detail)

    def soup(self, html):
        return inspect_page(html)

    def empty_or_changed(self, soup, markers: tuple[str, ...]):
        text = soup.get_text(" ", strip=True).lower()
        if not any(marker.lower() in text for marker in markers):
            raise ConnectorError("layout_changed", "No listing nodes or explicit empty-results marker found")
