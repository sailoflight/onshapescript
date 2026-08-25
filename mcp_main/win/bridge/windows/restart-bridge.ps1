# Force-restart the Onshape MCP Windows bridge and its automation Edge.
#
# This is the "一键自愈" script for a wedged bridge: it force-kills (NOT
# gracefully closes) both the automation Edge (the one using the onshape_profile
# user-data-dir) and any python running mcp_main\bridge\bridge_server.py, then starts a
# fresh bridge. Force-kill is deliberate — Onshape logs out when the browser
# closes gracefully; force-kill preserves the session files so the next launch
# restores the logged-in documents page via onshape_browser_mode/config/browser-state.json.
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\mcp_main\bridge\windows\restart-bridge.ps1
param(
    [int]$Port = 8766
)

$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$python = Join-Path $root '.venv\Scripts\pythonw.exe'
$bridge = Join-Path $root 'mcp_main\bridge\bridge_server.py'

Write-Host "[1/3] force-killing automation Edge (onshape_profile) ..."
Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" |
    Where-Object { $_.CommandLine -like '*onshape_profile*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Write-Host "[2/3] force-killing bridge server python/pythonw ..."
Get-CimInstance Win32_Process |
    Where-Object { $_.Name -in @('python.exe', 'pythonw.exe') -and
                   $_.CommandLine -like '*bridge_server.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Start-Sleep -Seconds 2

if (-not (Test-Path $python)) {
    throw "virtualenv windowless python not found: $python"
}
if (-not (Test-Path $bridge)) {
    throw "bridge server not found: $bridge"
}

Write-Host "[3/3] starting fresh bridge on 127.0.0.1:$Port (windowless) ..."
Start-Process -FilePath $python `
    -ArgumentList ('"{0}" {1}' -f $bridge, $Port) `
    -WorkingDirectory $root `
    -WindowStyle Hidden
Write-Host "done. logs: $root\mcp_main\bridge\logs\bridge-server.log"
