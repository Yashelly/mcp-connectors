param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    & $Python -c "import sys; assert sys.version_info >= (3, 12), 'Python 3.12+ required'"
    if ($LASTEXITCODE -ne 0) { throw "Python 3.12+ is required." }
    & $Python -m venv (Join-Path $ProjectRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed." }
}
& $VenvPython -m pip install -r (Join-Path $ProjectRoot "requirements.lock")
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
& $VenvPython -m pip install --no-deps -e $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw "Package installation failed." }
& $VenvPython -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "Chromium installation failed." }
Write-Host "Ready. Run scripts\check.ps1, then scripts\run.ps1."
