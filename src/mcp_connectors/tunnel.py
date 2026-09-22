"""Windows Credential Manager backed launcher for the OpenAI tunnel client."""
import argparse
import getpass
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import subprocess

from .autostart import contain_process_tree

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "tunnel.local.json"
TARGET = "Home MCP Tunnel"


def read_key(target):
    import win32cred

    blob = win32cred.CredRead(target, win32cred.CRED_TYPE_GENERIC)["CredentialBlob"]
    key = blob if isinstance(blob, str) else blob.decode("utf-16-le" if b"\x00" in blob else "utf-8-sig")
    key = key.strip()
    if not key or any(c.isspace() for c in key):
        raise ValueError("Credential must contain one nonempty API key.")
    return key


def load_config(path=CONFIG):
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    if not re.fullmatch(r"tunnel_[0-9a-f]{32}", config["tunnel_id"]):
        raise ValueError("Invalid tunnel ID.")
    executable = Path(config["executable"])
    if not executable.is_absolute() or not executable.is_file():
        raise ValueError("Tunnel executable must be an existing absolute file path.")
    port = config["port"]
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Invalid MCP port.")
    return config


def run_client(config, key, logger):
    env = dict(os.environ)
    env.update(CONTROL_PLANE_API_KEY=key, CONTROL_PLANE_TUNNEL_ID=config["tunnel_id"],
               MCP_SERVER_URL=f"http://127.0.0.1:{config['port']}/mcp")
    # Explicit flags override inherited profiles/environment for this installation.
    command = [config["executable"], "run", "--control-plane.tunnel-id", config["tunnel_id"],
               "--mcp.server-url", env["MCP_SERVER_URL"], "--health.listen-addr", "127.0.0.1:8080"]
    with subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding="utf-8", errors="replace",
                          creationflags=subprocess.CREATE_NO_WINDOW) as child:
        for line in child.stdout:
            # Never persist the runtime key, even if the child echoes it.
            logger.info("%s", line.rstrip().replace(key, "[REDACTED]"))
        return child.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--save-key", action="store_true")
    args = parser.parse_args()
    if args.save_key:
        import win32cred

        key = getpass.getpass("Runtime API key (hidden): ").strip()
        if not key or any(c.isspace() for c in key):
            parser.error("Enter one nonempty API key.")
        win32cred.CredWrite({"Type": win32cred.CRED_TYPE_GENERIC, "TargetName": TARGET,
                            "UserName": "api_key", "CredentialBlob": key.encode("utf-16-le"),
                            "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE}, 0)
        print("Saved credential: " + TARGET)
        return 0
    if args.check:
        try:
            load_config()
            read_key(TARGET)
        except Exception as error:
            print(f"Preflight failed ({type(error).__name__}). Check local configuration and the current-user credential.")
            return 1
        print("Configuration and current-user credential are available. Network access is not checked.")
        return 0
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    handler = RotatingFileHandler(logs / "tunnel.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    logger = logging.getLogger("tunnel")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        contain_process_tree()
        config = load_config()
        key = read_key(TARGET)
        result = run_client(config, key, logger)
        logger.info("Tunnel client exited with code %s; the enabled task will retry.", result)
        return result
    except Exception as error:
        # Exception messages from external libraries may contain credentials.
        logger.error("Tunnel launch failed (%s). Check local configuration, credentials and port availability.", type(error).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
