# Windows 侧浏览器桥接部署

浏览器自动化在 Windows 上运行：真实 Chrome/Edge 窗口 + 持久化登录 profile。
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
tools/bridge_server.py (Windows)  常驻监听；每个连接拉起一个 MCP 子进程
        │
        ▼
mcp_server.py (Windows .venv) → onshape_browser_mode → Chrome/Edge
```

- 默认端口：`8766`
- 单副本铁律：一个持久化浏览器 profile 只能被一个 MCP 进程持有；bridge 同一时刻只允许一个客户端。
- 仅回环 TCP，不暴露公网；Linux 侧零第三方依赖。

## Windows 一次性安装

```powershell
cd C:\MCP\onshapescript
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r tools\windows\requirements-browser.txt
```

**不下载浏览器**：直接复用 taobao-mcp 的浏览器配置思路，使用 Windows 本机已有 Chrome/Edge。
默认 `channel = "chrome"`；若本机只有 Edge，复制 `config\browser.local.toml.example` 为
`config\browser.local.toml` 即可（内容与 taobao Windows 配置一致）：

```toml
[browser]
executable_path = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
proxy_server = "http://127.0.0.1:10808"   # 本机 HTTP 代理，用于访问 Onshape
```

如果本机需要走代理才能访问 Onshape，把 `proxy_server` 设为本机 HTTP 代理地址
（v2rayN/clash 常见为 `http://127.0.0.1:10808`）；不需要则留空。

浏览器用户文件独立存放在 `user_data\onshape_profile`，不会混用系统默认浏览器 profile，
也不会与 taobao-mcp 的 `user_data\chrome_profile` 冲突。

## Windows 启动桥接服务

```powershell
cd C:\MCP\onshapescript
.\.venv\Scripts\python.exe .\tools\bridge_server.py 8766
```

或直接双击 `tools\windows\start-bridge.bat`。

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
- `setup-autostart.bat` 会同时**立即启动**桥接服务，因此也是“重启后/服务掉了”的一键恢复入口。
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

首次使用 `browser_session(action='login')` 时，Windows 桌面会弹出浏览器窗口，
人工完成 Onshape 登录（含 SSO/2FA）；登录态保存在 Windows 侧
`user_data\onshape_profile`，后续复用。

## 验证

Linux 侧可先跑探针：

```bash
python3 tools/mcp_probe.py
```
