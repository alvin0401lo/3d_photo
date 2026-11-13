param([string]$PythonPath = "")
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    if (-not $PythonPath) {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCommand) { $PythonPath = $pythonCommand.Source }
        else { throw 'Python 3.11 or 3.12 is required. Run this script with -PythonPath pointing to python.exe.' }
    }
    & $PythonPath -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
}
& '.\.venv\Scripts\python.exe' -m pip install --upgrade pip==26.3
if ($LASTEXITCODE -ne 0) { throw 'Could not update the project package installer.' }
& '.\.venv\Scripts\python.exe' -m pip install -r backend/requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
& '.\.venv\Scripts\python.exe' -m pip install -r backend/requirements-cpu.txt
if ($LASTEXITCODE -ne 0) { throw 'CPU model runtime installation failed.' }
& '.\.venv\Scripts\python.exe' scripts/fetch_models.py
if ($LASTEXITCODE -ne 0) { throw 'Model download failed.' }
if (-not (Test-Path -LiteralPath 'examples\kiara-panorama.jpg')) {
    & '.\.venv\Scripts\python.exe' scripts/fetch_panorama_example.py
    if ($LASTEXITCODE -ne 0) { throw 'Panorama example download failed.' }
}
if (-not (Test-Path -LiteralPath 'examples\cesium-man.glb')) {
    & '.\.venv\Scripts\python.exe' scripts/fetch_object_example.py
    if ($LASTEXITCODE -ne 0) { throw '3D character example download failed.' }
}
Push-Location frontend
try {
    npm.cmd ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }
Write-Output 'Setup complete. Double-click Start-DepthFrame.cmd to open the application.'
