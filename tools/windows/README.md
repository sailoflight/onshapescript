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
```

浏览器用户文件独立存放在 `user_data\onshape_profile`，不会混用系统默认浏览器 profile，
也不会与 taobao-mcp 的 `user_data\chrome_profile` 冲突。

## Windows 启动桥接服务

```powershell
cd C:\MCP\onshapescript
.\.venv\Scripts\python.exe .\tools\bridge_server.py 8766
```

建议用任务计划程序在登录时启动，保持常驻。

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
