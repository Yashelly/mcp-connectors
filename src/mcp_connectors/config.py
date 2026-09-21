from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    headless: bool = True
    timeout_ms: int = 30000
    locale: str = "lt-LT"

    @classmethod
    def from_env(cls) -> "Settings":
        raw = os.getenv("MCP_HEADLESS", "true").lower().strip()
        if raw not in {"true", "false"}:
            raise ValueError("MCP_HEADLESS must be true or false")
        timeout = int(os.getenv("MCP_BROWSER_TIMEOUT_MS", "30000"))
        if not 1000 <= timeout <= 120000:
            raise ValueError("MCP_BROWSER_TIMEOUT_MS must be between 1000 and 120000")
        return cls(
            headless=raw == "true",
            timeout_ms=timeout,
            locale=os.getenv("MCP_LOCALE", "lt-LT"),
        )
