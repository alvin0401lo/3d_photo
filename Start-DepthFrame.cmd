@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Setup-DepthFrame.ps1 first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\serve.py %*
if errorlevel 1 pause
