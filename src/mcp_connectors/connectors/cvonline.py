from .base import Connector, ConnectorInfo


class CVonlineConnector(Connector):
    info = ConnectorInfo("cvonline", "CVonline", "https://www.cvonline.lt", "jobs")
