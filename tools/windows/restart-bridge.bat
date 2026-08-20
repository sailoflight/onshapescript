@echo off
rem One-click force-restart of the Onshape MCP Windows bridge + automation Edge.
rem Force-kill preserves the Onshape login session (graceful close would log out).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart-bridge.ps1"
