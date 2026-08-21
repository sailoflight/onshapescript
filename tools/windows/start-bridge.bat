@echo off
rem Compatibility launcher. The persistent bridge runs through pythonw.exe,
rem so this cmd window closes immediately instead of remaining on screen.
wscript.exe //B //Nologo "%~dp0start-bridge-hidden.vbs" 8766
