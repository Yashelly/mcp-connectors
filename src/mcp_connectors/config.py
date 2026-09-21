from dataclasses import dataclass
import os
from pathlib import Path

PROFILE_ROOT = Path(__file__).resolve().parents[2] / ".browser_profiles"


@dataclass(frozen=True)
class Settings:
    headless: bool = False
    timeout_ms: int = 30000
    locale: str = "lt-LT"
    browser_channel: str = "chrome"
    profile_dir: Path | None = None
    verification_timeout_s: int = 120

    def __post_init__(self):
        if self.browser_channel not in {"chrome", "chromium"}:
            raise ValueError("MCP_BROWSER_CHANNEL must be chrome or chromium")
        if self.profile_dir is None:
            object.__setattr__(self, "profile_dir", PROFILE_ROOT / self.browser_channel)

    @classmethod
    def from_env(cls) -> "Settings":
        raw = os.getenv("MCP_HEADLESS", "false").lower().strip()
        if raw not in {"true", "false"}:
            raise ValueError("MCP_HEADLESS must be true or false")
        timeout = int(os.getenv("MCP_BROWSER_TIMEOUT_MS", "30000"))
        if not 1000 <= timeout <= 120000:
            raise ValueError("MCP_BROWSER_TIMEOUT_MS must be between 1000 and 120000")
        verification_timeout = int(os.getenv("MCP_VERIFICATION_TIMEOUT_SECONDS", "120"))
        if not 0 <= verification_timeout <= 600:
            raise ValueError("MCP_VERIFICATION_TIMEOUT_SECONDS must be between 0 and 600")
        channel = os.getenv("MCP_BROWSER_CHANNEL", "chrome").strip().lower()
        profile = os.getenv("MCP_BROWSER_PROFILE_DIR")
        return cls(
            headless=raw == "true",
            timeout_ms=timeout,
            locale=os.getenv("MCP_LOCALE", "lt-LT"),
            browser_channel=channel,
            profile_dir=Path(profile).expanduser().resolve() if profile else None,
            verification_timeout_s=verification_timeout,
        )
