"""Console-free Windows entry point for an interactive scheduled task."""
import argparse
import io
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys


class LogStream(io.TextIOBase):
    """Give console-oriented libraries a stream when pythonw has none."""

    def __init__(self, level: int):
        self.level = level

    @property
    def encoding(self):
        return "utf-8"

    def write(self, text):
        if text.strip():
            logging.getLogger("console").log(self.level, "%s", text.rstrip())
        return len(text)


def contain_process_tree():
    """Terminate browser descendants even if Task Scheduler kills Python."""
    import win32api
    import win32job

    job = win32job.CreateJobObject(None, "")
    limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
    limits["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
    win32job.AssignProcessToJobObject(job, win32api.GetCurrentProcess())
    # The OS closes this handle on process exit, including forced termination.
    # Detaching prevents normal Python scope cleanup from killing the parent
    # before its interpreter has finished shutting down.
    job.Detach()


def main():
    if sys.platform != "win32":
        raise RuntimeError("Scheduled autostart requires Windows.")
    parser = argparse.ArgumentParser(description="Run visible MCP without a console window")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--browser-channel", choices=("chrome", "chromium"), default="chrome")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    root = Path(__file__).resolve().parents[2]
    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    handler = RotatingFileHandler(logs / "autostart.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.stdout = LogStream(logging.INFO)
    sys.stderr = LogStream(logging.ERROR)
    try:
        contain_process_tree()
        os.environ["MCP_HEADLESS"] = "false"
        os.environ["MCP_BROWSER_CHANNEL"] = args.browser_channel
        # Explicitly use this installation's dedicated browser profile.
        os.environ["MCP_BROWSER_PROFILE_DIR"] = str(root / ".browser_profiles" / args.browser_channel)
        import uvicorn
        from .server import mcp

        logging.info("Starting interactive MCP on 127.0.0.1:%s using %s", args.port, args.browser_channel)
        # Keep server logs on the rotating file handler instead of replacing
        # them with Uvicorn's console handlers under pythonw.
        uvicorn.run(mcp.streamable_http_app(host="127.0.0.1"), host="127.0.0.1", port=args.port, log_config=None)
    except Exception:
        logging.exception("Autostart failed; Task Scheduler will retry while enabled.")
        raise


if __name__ == "__main__":
    main()
