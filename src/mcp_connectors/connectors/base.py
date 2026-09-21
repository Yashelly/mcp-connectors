from dataclasses import asdict, dataclass
from typing import Literal

from ..browser import BrowserRuntime


@dataclass(frozen=True)
class ConnectorInfo:
    id: str
    name: str
    website: str
    category: Literal["jobs", "cars"]
    status: str = "planned"


class Connector:
    """Contract for future adapters. Unimplemented operations fail explicitly."""

    info: ConnectorInfo

    def __init__(self, browser: BrowserRuntime) -> None:
        self.browser = browser

    def describe(self) -> dict[str, str]:
        return asdict(self.info)

    async def search(self, query: str, *, limit: int = 10) -> list[dict]:
        raise NotImplementedError(f"{self.info.id}: search is not implemented yet")

    async def get_listing(self, url: str) -> dict:
        raise NotImplementedError(f"{self.info.id}: get_listing is not implemented yet")
