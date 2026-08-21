# Windows 侧浏览器桥接部署

浏览器自动化在 Windows 上运行：真实 Edge 窗口 + 持久化登录 profile。
Linux/WSL 侧只运行 `tools/mcp_tcp_bridge.py` 做 stdio↔TCP 中继，不安装任何
浏览器内核依赖。

## 架构

```text
Linux MCP 客户端 (stdio)
        │ spawn
        ▼
tools/mcp_tcp_bridge.py (Linux)   stdio ↔ TCP
        │ 127.0.0.1:8766 (WSL2 镜像网络)
        ▼
tools/bridge_server.py (Windows)  常驻进程内 MCP dispatch（不拉起子进程）
        │
        ▼
mcp_main.server → onshape_browser_mode → Edge（浏览器随常驻进程存活）
```

- 默认端口：`8766`
- **浏览器必须由常驻进程持有**：Onshape WEB 端没有“保持登录”，浏览器一关立即登出。
  因此 bridge 在**自己的进程内**直接 dispatch JSON-RPC，客户端断开只关 socket、
  不关浏览器；客户端重连后登录态仍在。只有桥接进程退出（重启/关机）才会关浏览器。
- 单副本铁律：一个持久化浏览器 profile 只能被一个进程持有；bridge 同一时刻只允许一个客户端。
- 仅回环 TCP，不暴露公网；Linux 侧零第三方依赖。

## Windows 一次性安装

```powershell
cd C:\MCP\onshapescript
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r tools\windows\requirements-browser.txt
```

**不下载浏览器**：直接复用 taobao-mcp 的浏览器配置思路，使用 Windows 本机已有 Edge。
默认 `channel = "msedge"`。如需本机 HTTP 代理访问 Onshape，复制
`config\browser.local.toml.example` 为 `config\browser.local.toml` 并设置：

```toml
[browser]
proxy_server = "http://127.0.0.1:10808"   # 本机 HTTP 代理，用于访问 Onshape
```

（v2rayN/clash 常见为 `http://127.0.0.1:10808`；不需要代理则留空。）
也可以改用精确浏览器路径：`executable_path = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'`。

浏览器用户文件独立存放在 `user_data\onshape_profile`，不会混用系统默认浏览器 profile，
也不会与 taobao-mcp 的 `user_data\chrome_profile` 冲突。

## Windows 无窗口启动桥接服务

```powershell
cd C:\MCP\onshapescript
wscript.exe .\tools\windows\start-bridge-hidden.vbs 8766
```

- 推荐直接双击 `tools\windows\start-bridge-hidden.vbs`：桥接使用虚拟环境的
  `pythonw.exe` 后台运行，不创建 CMD/PowerShell/Python 控制台窗口。
- `start-bridge.bat` 是兼容入口，也会委托给隐藏 VBS；双击 BAT 时 CMD 可能短暂闪现，
  但不会留下常驻黑框。
- 隐藏的是**桥接控制台**，不是 Onshape 浏览器。首次登录、人工操作和浏览器工具仍会显示
  正常的 Edge 窗口。
- 运行日志继续写入 `outputs\bridge-server.log`；无窗口启动失败时先检查该文件，
  再用 `python.exe tools\bridge_server.py 8766` 前台诊断。

## 重启后如何自动恢复（与 taobao-mcp 同款方案）

taobao-mcp 并没有自定义的“一键恢复脚本”，它靠两层机制在重启后自愈：

1. **Windows 任务计划程序（登录时启动 + 失败自动重启）**：桥接服务常驻，
   开机登录后自动拉起，进程崩溃后每分钟重启一次。
2. **Linux 侧 MCP 客户端自动重连**：客户端插件自带指数退避重连，桥接服务
   恢复后自动重新发现工具，无需手工干预。

本仓库提供等价的一键配置脚本 `tools\windows\setup-autostart.bat`（双击即可）：

```powershell
# 或手动执行等价命令
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\windows\register-bridge-task.ps1
```

- 注册的计划任务名：`OnshapeMCPBridge`（登录时启动，失败后每 1 分钟重启，最多 999 次）。
  计划任务执行 `pythonw.exe`，登录后不会弹出桥接控制台。
- `setup-autostart.bat` 会同时**立即启动**桥接服务，因此也是“重启后/服务掉了”的一键恢复入口。
- **桥接卡死时的无窗口自愈**：双击 `tools\windows\restart-bridge-hidden.vbs`。
  `restart-bridge.bat` 是兼容入口，可能短暂闪现 CMD；需要前台诊断时再运行
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\windows\restart-bridge.ps1`。
  它会**强杀**自动化 Edge（`onshape_profile`）+ 旧 bridge，再启动新 bridge。
  强杀（而非优雅关闭）是刻意的：Onshape 关浏览器即登出，强杀保留会话文件，
  重启后靠 `config/browser-state.json` 恢复已登录的 documents 页。
- 移除自动启动：`powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\windows\register-bridge-task.ps1 -Uninstall`

## Linux/WSL 侧配置

MCP 客户端不直接启动 `mcp_server.py`，而是启动中继：

```json
{
  "mcpServers": {
    "onshape-featurescript": {
      "command": "python3",
      "args": ["/home/<user>/code/onshapescript/tools/mcp_tcp_bridge.py", "8766"],
      "cwd": "/home/<user>/code/onshapescript"
    }
  }
}
```

首次使用 `browser_session(action='login')` 时，Windows 桌面会弹出 Edge 窗口，
人工完成 Onshape 登录（含 SSO/2FA）。登录态保存在 Windows 侧
`user_data\onshape_profile`，并且只要桥接进程还活着就一直有效：

- MCP 客户端断开/重连、DSH/Codex 重启：**不影响登录态**（浏览器没关）。
- Windows 重启或桥接进程被杀：浏览器关闭 → Onshape 登出，需重新
  `browser_session(action='login')` 登录一次。这是 Onshape 的限制，无法绕开。

## 验证

Linux 侧可先跑探针：

```bash
python3 tools/mcp_probe.py
```
