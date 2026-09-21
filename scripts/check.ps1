$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) { throw "Run scripts\setup.ps1 first." }
& $VenvPython -m pip check
if ($LASTEXITCODE -ne 0) { throw "Dependency check failed." }
& $VenvPython -m unittest discover -s (Join-Path $ProjectRoot "tests") -v
if ($LASTEXITCODE -ne 0) { throw "Tests failed." }
& $VenvPython (Join-Path $PSScriptRoot "smoke.py") --all-transports
if ($LASTEXITCODE -ne 0) { throw "MCP/browser smoke test failed." }
