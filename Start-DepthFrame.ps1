param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { throw 'Run Setup-DepthFrame.ps1 first.' }
if ($NoBrowser) { & '.\.venv\Scripts\python.exe' scripts/serve.py --no-browser }
else { & '.\.venv\Scripts\python.exe' scripts/serve.py }
