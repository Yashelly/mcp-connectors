from .base import Connector, ConnectorInfo


class AutogidasConnector(Connector):
    info = ConnectorInfo("autogidas", "Autogidas", "https://autogidas.lt", "cars")
