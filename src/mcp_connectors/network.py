"""Chromium request-stage guard: redirects pause again before network access."""
from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError

from .errors import ConnectorError
from .security import public_host, validate_url


class NetworkGuard:
    def __init__(self, session, main_frame: str, hosts: frozenset[str]):
        self.session = session
        self.main_frame = main_frame
        self.hosts = hosts
        self.checked: set[str] = set()
        self.errors: list[ConnectorError] = []
        self.document_requests = 0

    async def paused(self, event):
        request_id = event["requestId"]
        main = event.get("resourceType") == "Document" and event.get("frameId") == self.main_frame
        try:
            if event.get("resourceType") in {"Image", "Media", "Font"} or (event.get("resourceType") == "Document" and not main):
                await self.session.send("Fetch.failRequest", {"requestId": request_id, "errorReason": "Aborted"})
                return
            url = validate_url(event["request"]["url"], self.hosts if main else None)
            host = urlsplit(url).hostname
            if host not in self.checked:
                await public_host(host)
                self.checked.add(host)
            if main:
                self.document_requests += 1
                if self.document_requests > 8:
                    raise ConnectorError("network_error", "Navigation/redirect limit exceeded")
            await self.session.send("Fetch.continueRequest", {"requestId": request_id})
        except ConnectorError as error:
            if main:
                self.errors.append(error)
            await self.session.send("Fetch.failRequest", {"requestId": request_id, "errorReason": "BlockedByClient"})
        except PlaywrightError:
            # Context may close while an optional resource is paused.
            return
