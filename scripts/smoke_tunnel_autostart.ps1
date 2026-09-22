$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$TaskName = 'MCP Tunnel Smoke ' + [guid]::NewGuid().ToString('N')
$Scratch = Join-Path ([System.IO.Path]::GetTempPath()) $TaskName
New-Item -ItemType Directory -Path $Scratch | Out-Null
$Registered = $false
try {
    # Python acts as a local dummy client. No real credential or network is used.
    @'
import os, pathlib, time
assert os.environ['CONTROL_PLANE_API_KEY'] == 'test-only-placeholder'
pathlib.Path('client.pid').write_text(str(os.getpid()))
while True:
    time.sleep(1)
'@ | Set-Content -LiteralPath (Join-Path $Scratch 'run') -Encoding UTF8
    @'
import pathlib, sys
from mcp_connectors import tunnel
tunnel.ROOT = pathlib.Path.cwd()
tunnel.load_config = lambda: {'executable': sys.executable, 'tunnel_id': 'tunnel_' + 'a' * 32, 'port': 8765}
tunnel.read_key = lambda target: 'test-only-placeholder'
raise SystemExit(tunnel.main())
'@ | Set-Content -LiteralPath (Join-Path $Scratch 'runner.py') -Encoding UTF8
    [xml]$Definition = & (Join-Path $PSScriptRoot 'tunnel-autostart.ps1') -Action Export
    $Definition.Task.Actions.Exec.Arguments = '"' + (Join-Path $Scratch 'runner.py') + '"'
    $Definition.Task.Actions.Exec.WorkingDirectory = [string]$Scratch
    Register-ScheduledTask -TaskName $TaskName -Xml $Definition.OuterXml | Out-Null
    $Registered = $true
    Start-ScheduledTask -TaskName $TaskName
    $PidFile = Join-Path $Scratch 'client.pid'
    $Deadline = (Get-Date).AddSeconds(30)
    while (-not (Test-Path -LiteralPath $PidFile)) {
        if ((Get-Date) -gt $Deadline) { throw 'Dummy client did not start.' }
        Start-Sleep -Seconds 1
    }
    $FirstClient = [int](Get-Content -LiteralPath $PidFile)
    Stop-Process -Id $FirstClient -Force
    $Deadline = (Get-Date).AddSeconds(85)
    do {
        Start-Sleep -Seconds 1
        $NextClient = [int](Get-Content -LiteralPath $PidFile)
        if ((Get-Date) -gt $Deadline) { throw 'Task did not recover after client exit.' }
    } while ($NextClient -eq $FirstClient)
    if (-not (Get-Process -Id $NextClient -ErrorAction SilentlyContinue)) { throw 'Recovered client is not running.' }
    Disable-ScheduledTask -TaskName $TaskName | Out-Null
    Stop-ScheduledTask -TaskName $TaskName
    $Deadline = (Get-Date).AddSeconds(10)
    while (Get-Process -Id $NextClient -ErrorAction SilentlyContinue) {
        if ((Get-Date) -gt $Deadline) { throw 'Task stop left its client running.' }
        Start-Sleep -Milliseconds 200
    }
    Write-Output 'Tunnel task smoke passed: child launch, crash recovery, descendant cleanup.'
} finally {
    if ($Registered) {
        Disable-ScheduledTask -TaskName $TaskName | Out-Null
        Stop-ScheduledTask -TaskName $TaskName
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
    # Only remove this run's uniquely named directory under the resolved temp root.
    $ResolvedScratch = [System.IO.Path]::GetFullPath($Scratch)
    $TempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if (-not $ResolvedScratch.StartsWith($TempRoot, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe cleanup path.' }
    Remove-Item -LiteralPath $ResolvedScratch -Recurse -Force
}

