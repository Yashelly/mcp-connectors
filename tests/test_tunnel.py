"""Tunnel secret handling, launch contract and Windows task recovery checks."""
import io
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import xml.etree.ElementTree as ET

from mcp_connectors import tunnel

ROOT = Path(__file__).resolve().parents[1]
NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


@unittest.skipUnless(os.name == "nt", "Windows credential and scheduler integration")
class TunnelTests(unittest.TestCase):
    def test_preflight_does_not_print_external_error_details(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["tunnel", "--check"]), patch.object(tunnel, "load_config", return_value={}):
            with patch.object(tunnel, "read_key", side_effect=RuntimeError("sensitive-value")), patch("sys.stdout", output):
                self.assertEqual(tunnel.main(), 1)
        self.assertNotIn("sensitive-value", output.getvalue())
        self.assertIn("Preflight failed", output.getvalue())

    def test_credential_encodings_and_empty_value(self):
        for blob in ("example-key", b"example-key", "example-key".encode("utf-16-le")):
            with patch("win32cred.CredRead", return_value={"CredentialBlob": blob}):
                self.assertEqual(tunnel.read_key("test"), "example-key")
        with patch("win32cred.CredRead", return_value={"CredentialBlob": b""}):
            with self.assertRaises(ValueError):
                tunnel.read_key("test")

    def test_config_bom_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = {"executable": sys.executable, "tunnel_id": "tunnel_" + "a" * 32, "port": 8765}
            path.write_text(json.dumps(config), encoding="utf-8-sig")
            self.assertEqual(tunnel.load_config(path), config)
            for name, value in (("port", 0), ("port", True), ("tunnel_id", "bad"), ("executable", "relative.exe")):
                path.write_text(json.dumps(dict(config, **{name: value})), encoding="utf-8")
                with self.assertRaises(ValueError):
                    tunnel.load_config(path)

    def test_child_only_key_redaction_and_exit_propagation(self):
        key = "dummy-secret-for-testing"
        child = MagicMock()
        child.__enter__.return_value = child
        child.stdout = io.StringIO("unexpected echo: " + key + "\n")
        child.wait.return_value = 7
        config = {"executable": sys.executable, "tunnel_id": "tunnel_" + "a" * 32, "port": 8765}
        before = dict(os.environ)
        with patch.object(tunnel.subprocess, "Popen", return_value=child) as spawn:
            with self.assertLogs("tunnel-test", level="INFO") as logs:
                result = tunnel.run_client(config, key, logging.getLogger("tunnel-test"))
        self.assertEqual(result, 7)
        self.assertEqual(dict(os.environ), before)
        self.assertNotIn(key, str(spawn.call_args.args))
        self.assertEqual(spawn.call_args.kwargs["env"]["CONTROL_PLANE_API_KEY"], key)
        self.assertNotIn(key, "".join(logs.output))
        self.assertIn("[REDACTED]", "".join(logs.output))

    def test_task_xml(self):
        result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                 "-File", "scripts/tunnel-autostart.ps1", "-Action", "Export"],
                                cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        root = ET.fromstring(result.stdout)
        def value(path):
            return root.findtext(path, namespaces=NS)
        self.assertEqual(value("t:Principals/t:Principal/t:LogonType"), "InteractiveToken")
        self.assertEqual(value("t:Settings/t:MultipleInstancesPolicy"), "IgnoreNew")
        self.assertEqual(value("t:Settings/t:ExecutionTimeLimit"), "PT0S")
        self.assertEqual(value("t:Triggers/t:TimeTrigger/t:Repetition/t:Interval"), "PT1M")
        self.assertIsNone(value("t:Triggers/t:TimeTrigger/t:Repetition/t:Duration"))
        self.assertEqual(value("t:Actions/t:Exec/t:Arguments"), "-m mcp_connectors.tunnel")
        self.assertNotIn("CONTROL_PLANE_API_KEY", result.stdout)

    def test_stop_disables_recovery_before_termination(self):
        script = r'''
Import-Module ScheduledTasks
$Calls = [System.Collections.Generic.List[string]]::new()
function Get-ScheduledTask { param($TaskPath) [pscustomobject]@{TaskName=$TaskName; Description=$Description} }
function Disable-ScheduledTask { param($InputObject) $Calls.Add('disable') }
function Stop-ScheduledTask { param($InputObject) $Calls.Add('stop') }
& ./scripts/tunnel-autostart.ps1 -Action Stop | Out-Null
$Calls -join ','
'''
        result = subprocess.run(["powershell", "-NoProfile", "-Command", script], cwd=ROOT,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("disable,stop", result.stdout)
