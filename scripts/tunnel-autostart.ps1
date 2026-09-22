param(
    [ValidateSet("Install", "Status", "Stop", "Start", "Remove", "Export")]
    [string]$Action = "Install",
    [ValidateRange(1, 65535)][int]$Port = 8765,
    [string]$TunnelId,
    [string]$ClientPath = "$env:USERPROFILE\mcp-tunnel\tunnel-client.exe"
)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$UserSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value

# Separate users and checkouts without overwriting unrelated scheduled tasks.
$Hasher = [System.Security.Cryptography.SHA256]::Create()
try {
    $IdentityBytes = [System.Text.Encoding]::UTF8.GetBytes("$UserSid|$($ProjectRoot.ToLowerInvariant())")
    $TaskSuffix = ([System.BitConverter]::ToString($Hasher.ComputeHash($IdentityBytes))).Replace("-", "").Substring(0, 12)
} finally {
    $Hasher.Dispose()
}
$TaskName = "MCP Tunnel $TaskSuffix"
$Description = "MCP Tunnel interactive autostart: $ProjectRoot; user: $UserSid"

if ($Action -in @("Install", "Export")) {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
    if (-not (Test-Path -LiteralPath $VenvPython)) { throw "Run scripts\setup.ps1 first." }
    $Arguments = '-m mcp_connectors.tunnel'
    $TaskAction = New-ScheduledTaskAction -Execute $VenvPython -Argument $Arguments -WorkingDirectory $ProjectRoot
    $Principal = New-ScheduledTaskPrincipal -UserId $UserSid -LogonType Interactive -RunLevel Limited
    $LogonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $UserSid
    # Omitting RepetitionDuration makes the recovery trigger repeat indefinitely.
    $RecoveryTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
    $Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $Definition = New-ScheduledTask -Action $TaskAction -Principal $Principal -Trigger @($LogonTrigger, $RecoveryTrigger) -Settings $Settings -Description $Description
    if ($Action -eq "Export") {
        $Definition | Export-ScheduledTask
        return
    }
}

$Existing = Get-ScheduledTask -TaskPath "\" | Where-Object { $_.TaskName -eq $TaskName }
if ($Existing -and $Existing.Description -ne $Description) {
    throw "Task name collision. Refusing to change an unrelated scheduled task: $TaskName"
}

switch ($Action) {
    "Install" {
        $ConfigPath = Join-Path $ProjectRoot "tunnel.local.json"
        if ($TunnelId) {
            if ($TunnelId -cnotmatch '^tunnel_[0-9a-f]{32}$') { throw "Invalid tunnel ID." }
            $ResolvedClient = (Resolve-Path -LiteralPath $ClientPath).Path
            if (-not (Test-Path -LiteralPath $ResolvedClient -PathType Leaf)) { throw "Tunnel executable not found." }
            @{ tunnel_id = $TunnelId; executable = $ResolvedClient; port = $Port } | ConvertTo-Json | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
        }
        if (-not (Test-Path -LiteralPath $ConfigPath)) { throw "Provide -TunnelId on first installation." }
        & (Join-Path $ProjectRoot ".venv\Scripts\python.exe") -m mcp_connectors.tunnel --check
        if ($LASTEXITCODE -ne 0) { throw "Tunnel preflight failed. Check configuration and Windows Credential Manager under this account." }
        if ($Existing) {
            Disable-ScheduledTask -InputObject $Existing | Out-Null
            Stop-ScheduledTask -InputObject $Existing
        }
        Register-ScheduledTask -TaskName $TaskName -TaskPath "\" -InputObject $Definition -Force | Out-Null
        Start-ScheduledTask -TaskName $TaskName -TaskPath "\"
        Write-Host "Installed and started: $TaskName"
        Write-Host "Starts at user logon; retries every minute while logged in. Readiness: http://127.0.0.1:8080/readyz"
        Write-Host "Reads Home MCP Tunnel from current-user Credential Manager. Logs: logs/tunnel.log. Windows sign-in is required."
    }
    "Status" {
        if (-not $Existing) { Write-Host "Autostart is not installed for this checkout and user."; return }
        $Info = Get-ScheduledTaskInfo -InputObject $Existing
        [pscustomobject]@{
            TaskName = $TaskName
            State = $Existing.State
            LastRunTime = $Info.LastRunTime
            LastTaskResult = $Info.LastTaskResult
            NextRunTime = $Info.NextRunTime
        }
    }
    "Stop" {
        if (-not $Existing) { Write-Host "Autostart is not installed for this checkout and user."; return }
        Disable-ScheduledTask -InputObject $Existing | Out-Null
        Stop-ScheduledTask -InputObject $Existing
        Write-Host "Stopped and disabled: $TaskName"
    }
    "Start" {
        if (-not $Existing) { throw "Run scripts\tunnel-autostart.ps1 -Action Install first." }
        Enable-ScheduledTask -InputObject $Existing | Out-Null
        Start-ScheduledTask -InputObject $Existing
        Write-Host "Enabled and started: $TaskName"
    }
    "Remove" {
        if (-not $Existing) { Write-Host "Autostart is not installed for this checkout and user."; return }
        Disable-ScheduledTask -InputObject $Existing | Out-Null
        Stop-ScheduledTask -InputObject $Existing
        Unregister-ScheduledTask -InputObject $Existing -Confirm:$false
        Write-Host "Removed: $TaskName"
    }
}
