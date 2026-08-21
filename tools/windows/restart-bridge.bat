@echo off
rem One-click force-restart of the Onshape MCP Windows bridge + automation Edge.
rem Force-kill preserves the Onshape login session (graceful close would log out).
wscript.exe //B //Nologo "%~dp0restart-bridge-hidden.vbs" 8766
