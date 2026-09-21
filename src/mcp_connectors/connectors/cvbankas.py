from .base import Connector, ConnectorInfo


class CVbankasConnector(Connector):
    info = ConnectorInfo("cvbankas", "CVbankas", "https://www.cvbankas.lt", "jobs")
