"""Validate real Task Scheduler definitions without installing persistent tasks."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


@unittest.skipUnless(os.name == "nt", "Windows Task Scheduler is required")
class AutostartTests(unittest.TestCase):
    def powershell(self, *args):
        return subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", *args],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def test_interactive_recovery_definition(self):
        result = self.powershell(
            "-File", "scripts/autostart.ps1", "-Action", "Export",
            "-Port", "8766", "-BrowserChannel", "chromium",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        task = ET.fromstring(result.stdout)

        def value(path):
            return task.findtext(path, namespaces=NS)

        self.assertEqual(value("t:Principals/t:Principal/t:LogonType"), "InteractiveToken")
        self.assertEqual(value("t:Principals/t:Principal/t:RunLevel"), "LeastPrivilege")
        self.assertTrue(value("t:Triggers/t:LogonTrigger/t:UserId"))
        self.assertEqual(value("t:Triggers/t:TimeTrigger/t:Repetition/t:Interval"), "PT1M")
        self.assertIsNone(value("t:Triggers/t:TimeTrigger/t:Repetition/t:Duration"))
        self.assertIsNone(value("t:Triggers/t:TimeTrigger/t:EndBoundary"))
        self.assertEqual(value("t:Settings/t:ExecutionTimeLimit"), "PT0S")
        self.assertEqual(value("t:Settings/t:MultipleInstancesPolicy"), "IgnoreNew")
        self.assertEqual(value("t:Settings/t:DisallowStartIfOnBatteries"), "false")
        self.assertEqual(value("t:Settings/t:StopIfGoingOnBatteries"), "false")
        args = value("t:Actions/t:Exec/t:Arguments")
        self.assertEqual(value("t:Actions/t:Exec/t:Command"), str(ROOT / ".venv" / "Scripts" / "pythonw.exe"))
        self.assertEqual(args, "-m mcp_connectors.autostart --browser-channel chromium --port 8766")
        self.assertEqual(value("t:Actions/t:Exec/t:WorkingDirectory"), str(ROOT))

    def management(self, action, existing="owned"):
        # Mock only registration and lifecycle mutations. Task construction uses
        # the installed Windows ScheduledTasks module and its real CIM objects.
        harness = r'''
$ErrorActionPreference = 'Stop'
Import-Module ScheduledTasks
$Calls = [System.Collections.Generic.List[string]]::new()
function Get-ScheduledTask {
    param($TaskPath)
    if ($ExistingKind -ne 'missing') {
        $Owner = if ($ExistingKind -eq 'owned') { $Description } else { 'Unrelated task' }
        [pscustomobject]@{ TaskName = $TaskName; Description = $Owner }
    }
}
function Disable-ScheduledTask { param($InputObject) $Calls.Add('disable') }
function Stop-ScheduledTask { param($InputObject) $Calls.Add('stop') }
function Enable-ScheduledTask { param($InputObject) $Calls.Add('enable') }
function Start-ScheduledTask { param($InputObject, $TaskName, $TaskPath) $Calls.Add('start') }
function Unregister-ScheduledTask { param($InputObject, [switch]$Confirm) $Calls.Add('remove') }
function Register-ScheduledTask { param($InputObject, $TaskName, $TaskPath, [switch]$Force) $Calls.Add('register') }
try {
    & ./scripts/autostart.ps1 -Action $RequestedAction -BrowserChannel chromium
} finally {
    Write-Output ('CALLS=' + ($Calls -join ','))
}
'''
        return self.powershell(
            "-Command",
            f"$ExistingKind='{existing}'; $RequestedAction='{action}';\n" + harness,
        )

    def test_stop_disables_recovery_before_termination(self):
        result = self.management("Stop")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CALLS=disable,stop", result.stdout)

    def test_remove_disables_and_stops_before_unregistering(self):
        result = self.management("Remove")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CALLS=disable,stop,remove", result.stdout)

    def test_reinstall_restarts_existing_task(self):
        result = self.management("Install")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CALLS=disable,stop,register,start", result.stdout)

    def test_name_collision_does_not_modify_unrelated_task(self):
        result = self.management("Remove", existing="unrelated")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing to change an unrelated scheduled task", result.stderr)
        self.assertIn("CALLS=\n", result.stdout)

    def test_forced_exit_terminates_descendants(self):
        import win32api
        import win32con
        import win32event

        code = """
from pathlib import Path
import subprocess, sys, time
from mcp_connectors.autostart import contain_process_tree
contain_process_tree()
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'],
                         creationflags=subprocess.CREATE_NO_WINDOW)
Path(sys.argv[1]).write_text(str(child.pid))
time.sleep(120)
"""
        with tempfile.TemporaryDirectory() as directory:
            pidfile = Path(directory) / "child.pid"
            parent = subprocess.Popen(
                [sys.executable, "-c", code, str(pidfile)], cwd=ROOT,
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            handle = None
            try:
                deadline = time.monotonic() + 10
                while not pidfile.exists() and time.monotonic() < deadline:
                    self.assertIsNone(parent.poll(), "Parent exited before creating its child")
                    time.sleep(0.05)
                self.assertTrue(pidfile.exists(), "Parent did not create a child")
                handle = win32api.OpenProcess(win32con.SYNCHRONIZE | win32con.PROCESS_TERMINATE, False, int(pidfile.read_text()))
                parent.terminate()
                parent.wait(timeout=5)
                self.assertEqual(win32event.WaitForSingleObject(handle, 5000), win32event.WAIT_OBJECT_0)
            finally:
                if parent.poll() is None:
                    parent.kill()
                    parent.wait(timeout=5)
                if handle is not None:
                    if win32event.WaitForSingleObject(handle, 0) != win32event.WAIT_OBJECT_0:
                        win32api.TerminateProcess(handle, 1)
                    handle.Close()


if __name__ == "__main__":
    unittest.main()
