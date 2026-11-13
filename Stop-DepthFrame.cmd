@echo off
cd /d "%~dp0"
if not exist "storage" exit /b 0
type nul > "storage\stop-application"
echo Stop requested. DepthFrame will finish shutting down its worker and server.
