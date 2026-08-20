@echo off
set ROOT=%~dp0..\..
cd /d "%ROOT%"
".venv\Scripts\python.exe" "tools\bridge_server.py" 8766
