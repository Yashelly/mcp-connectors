from .base import Connector, ConnectorInfo


class AutopliusConnector(Connector):
    info = ConnectorInfo("autoplius", "Autoplius", "https://autoplius.lt", "cars")
