# Opt-in integration test: installs a temporary task and removes it in finally.
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$TaskName = "MCP Connectors Smoke $([guid]::NewGuid().ToString('N'))"
$Socket = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$Socket.Start()
$Port = $Socket.LocalEndpoint.Port
$Socket.Stop()

function Test-EndpointPort {
    $Client = [System.Net.Sockets.TcpClient]::new()
    try {
        $Pending = $Client.ConnectAsync("127.0.0.1", $Port)
        return ($Pending.Wait(200) -and $Client.Connected)
    } catch {
        return $false
    } finally {
        $Client.Dispose()
    }
}

function Wait-EndpointPort([bool]$Open, [int]$Seconds) {
    $Deadline = (Get-Date).AddSeconds($Seconds)
    do {
        if ((Test-EndpointPort) -eq $Open) { return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $Deadline)
    throw "Endpoint did not reach open=$Open within $Seconds seconds."
}

$Registered = $false
try {
    [xml]$Definition = (& (Join-Path $PSScriptRoot "autostart.ps1") -Action Export -Port $Port -BrowserChannel chromium | Out-String)
    $Definition.Task.RegistrationInfo.Description = "Temporary MCP Connectors autostart verification"
    Register-ScheduledTask -TaskName $TaskName -TaskPath "\" -Xml $Definition.OuterXml | Out-Null
    $Registered = $true
    Start-ScheduledTask -TaskName $TaskName -TaskPath "\"
    Wait-EndpointPort -Open $true -Seconds 20
    & $VenvPython (Join-Path $PSScriptRoot "smoke.py") --http-url "http://127.0.0.1:$Port/mcp"
    if ($LASTEXITCODE -ne 0) { throw "Scheduled MCP/browser check failed." }
    Write-Host "Scheduled MCP and visible offline Chromium passed."

    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen
    Stop-Process -Id $Listener.OwningProcess -Force
    Wait-EndpointPort -Open $false -Seconds 10
    Write-Host "Simulated process failure; waiting for the next one-minute recovery trigger."
    Wait-EndpointPort -Open $true -Seconds 85
    & $VenvPython (Join-Path $PSScriptRoot "smoke.py") --http-url "http://127.0.0.1:$Port/mcp"
    if ($LASTEXITCODE -ne 0) { throw "MCP did not recover after process failure." }
    Write-Host "Automatic recovery passed."

    Disable-ScheduledTask -TaskName $TaskName -TaskPath "\" | Out-Null
    Stop-ScheduledTask -TaskName $TaskName -TaskPath "\"
    Wait-EndpointPort -Open $false -Seconds 10
    Write-Host "Stopping the scheduled task released the endpoint."
} finally {
    if ($Registered) {
        Disable-ScheduledTask -TaskName $TaskName -TaskPath "\" | Out-Null
        Stop-ScheduledTask -TaskName $TaskName -TaskPath "\"
        Unregister-ScheduledTask -TaskName $TaskName -TaskPath "\" -Confirm:$false
    }
}
