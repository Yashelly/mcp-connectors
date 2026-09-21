from ..browser import BrowserRuntime
from .autogidas import AutogidasConnector
from .autoplius import AutopliusConnector
from .base import Connector
from .cvbankas import CVbankasConnector
from .cvmarket import CVmarketConnector
from .cvonline import CVonlineConnector


def create_connectors(browser: BrowserRuntime) -> dict[str, Connector]:
    adapters = (
        CVbankasConnector, CVonlineConnector, AutogidasConnector,
        CVmarketConnector, AutopliusConnector,
    )
    return {adapter.info.id: adapter(browser) for adapter in adapters}
