from .models import SourceError, Status


class ConnectorError(Exception):
    def __init__(self, code: Status, message: str, url: str | None = None,
                 http_status: int | None = None):
        super().__init__(message)
        self.detail = SourceError(code=code, message=message, url=url, http_status=http_status)
