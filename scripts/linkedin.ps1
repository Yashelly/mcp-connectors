param(
    [ValidateSet("Setup", "Login", "Run")][string]$Action = "Run",
    [string]$Python = "python",
    [ValidateRange(1, 65535)][int]$Port = 8001,
    [string]$StateRoot,
    [string]$ChromePath
)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvRoot = Join-Path $ProjectRoot ".venv-linkedin"
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"

if ($Action -eq "Setup") {
    $InstallerPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $InstallerPython)) { throw "Run scripts\setup.ps1 first." }
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        & $Python -c "import sys; assert (3, 12, 4) <= sys.version_info < (3, 15), 'LinkedIn MCP requires Python 3.12.4 through 3.14'"
        if ($LASTEXITCODE -ne 0) { throw "Pass -Python with a Python 3.12.4 through 3.14 executable." }
        & $Python -m venv --without-pip $VenvRoot
        if ($LASTEXITCODE -ne 0) { throw "LinkedIn venv creation failed." }
    }
    & $VenvPython -c "import sys; assert (3, 12, 4) <= sys.version_info < (3, 15), 'LinkedIn MCP requires Python 3.12.4 through 3.14'"
    if ($LASTEXITCODE -ne 0) { throw "The existing LinkedIn venv uses an unsupported Python version." }
    & $InstallerPython -m pip --python $VenvPython install -r (Join-Path $ProjectRoot "requirements.linkedin.lock")
    if ($LASTEXITCODE -ne 0) { throw "LinkedIn dependency installation failed." }
    & $InstallerPython -m pip --python $VenvPython check
    if ($LASTEXITCODE -ne 0) { throw "LinkedIn dependency check failed." }
    Write-Host "LinkedIn MCP installed. Run scripts\linkedin.ps1 -Action Login, then -Action Run."
    exit 0
}
if (-not (Test-Path -LiteralPath $VenvPython)) { throw "Run scripts\linkedin.ps1 -Action Setup first." }

if (-not $StateRoot) {
    $UserSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $StateRoot = Join-Path ([Environment]::GetFolderPath("CommonApplicationData")) "MCPConnectors-LinkedIn-$UserSid"
}
$StateRoot = [System.IO.Path]::GetFullPath($StateRoot)
& $VenvPython (Join-Path $PSScriptRoot "linkedin_state.py") $StateRoot
if ($LASTEXITCODE -ne 0) { throw "LinkedIn private state preflight failed. Existing directory permissions were not changed." }
if (-not $ChromePath) {
    $Candidates = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    $ChromePath = $Candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $ChromePath -or -not (Test-Path -LiteralPath $ChromePath -PathType Leaf)) {
    throw "Install Google Chrome or pass -ChromePath with a Chromium executable."
}
# The upstream owns this isolated profile root, including any session rotation.
# It must not share a parent with the existing site profiles or personal files.
$Profile = Join-Path $StateRoot "session\profile"
$InstallerTemp = Join-Path $StateRoot "installer"
$Arguments = @("-m", "linkedin_mcp_server", "--no-auto-import", "--no-headless", "--user-data-dir", $Profile,
    "--chrome-path", $ChromePath, "--installer-temp-dir", $InstallerTemp)
if ($Action -eq "Login") {
    $Arguments += "--login"
} else {
    $Arguments += @("--transport", "streamable-http", "--host", "127.0.0.1", "--port", "$Port", "--path", "/mcp")
}
& $VenvPython @Arguments
exit $LASTEXITCODE
