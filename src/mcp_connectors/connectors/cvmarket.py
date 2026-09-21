from .base import Connector, ConnectorInfo


class CVmarketConnector(Connector):
    info = ConnectorInfo("cvmarket", "CVmarket", "https://www.cvmarket.lt", "jobs")
