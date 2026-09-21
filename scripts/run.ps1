param(
    [ValidateSet("stdio", "streamable-http")][string]$Transport = "streamable-http",
    [ValidateRange(1, 65535)][int]$Port = 8765
)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) { throw "Run scripts\setup.ps1 first." }
& $VenvPython -m mcp_connectors --transport $Transport --port $Port
exit $LASTEXITCODE
