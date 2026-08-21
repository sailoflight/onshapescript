# 桥接目录：WSL 中继 + Windows 主体

> 通用 WIN-WSL 桥接架构协议见同目录 `ARCHITECTURE.md`（可复用于其他同架构 MCP）；
> 本文只写本项目的具体接线与维护规则。

## 职责边界（运行时）

| 对象 | 运行位置 | 角色 |
|---|---|---|
| `mcp_tcp_bridge.py` | **WSL/Linux（DSH 里）** | 唯一 WSL 运行时：stdio↔TCP 中继，连 `127.0.0.1:8766`，纯 stdlib |
| `bridge_server.py` | **Windows** | 常驻 TCP MCP 主体：`mcp_main.server.dispatch()` + 浏览器会话 |
| `mcp_main/server.py`（TOOLS/HANDLERS） | Windows 主体内 | 52 个 MCP 工具本体 |
| `onshape_browser_mode/` + Playwright | Windows 主体内 | Edge 浏览器自动化 |
| `windows/*` | Windows 部署 | 无窗口启动/重启/自愈脚本 |

- WSL 仓库是**开发仓库**：开发完成后同步到 Windows 部署副本
  （`C:\MCP\onshapescript`，非 git 仓库）。
- WSL 只执行中继脚本；**不要**在 WSL 运行 `python -m mcp_main`（那是完整 stdio
  MCP 主体，浏览器工具需要 Windows 上的 Playwright/Edge）。
- 中继脚本必须保持**纯 stdlib**（`os/select/socket/sys`），不得引入
  Playwright 或任何 MCP 主体依赖。

## WSL DSH 接入（把中继 MCP 装给 WSL 里运行的 DSH）

DSH 的 MCP 配置指向中继脚本，而不是直接起 MCP 包：

```json
{
  "mcpServers": {
    "onshape-featurescript": {
      "command": "python3",
      "args": ["/home/<user>/code/onshapescript/mcp_main/bridge/mcp_tcp_bridge.py", "8766"],
      "cwd": "/home/<user>/code/onshapescript"
    }
  }
}
```

要点：

- `args` 里的脚本路径与 `cwd` 用 WSL 内绝对路径（开发仓库位置）。
- 端口默认 `8766`，与 Windows 侧 `bridge_server.py` 一致。
- 中继是薄层：不装 Playwright、不持浏览器、不缓存登录态；登录态在 Windows 侧
  `onshape_browser_mode\user_data\onshape_profile`。
- Windows 桥接未启动时，中继 10 秒连不上即报错退出；先启动 Windows 桥接
  （`start-bridge-hidden.vbs` 或任务计划 `OnshapeMCPBridge`）。

## 维护规则

1. 改中继：只动 `mcp_tcp_bridge.py`，保持 stdlib-only；改完在 WSL 跑
   `python3 mcp_main/bridge/mcp_tcp_bridge.py 8766` 冒烟。
2. 改 MCP 主体（`mcp_main/server.py`、`onshape_browser_mode/*`、`bridge_server.py`）：
   在 WSL 跑离线测试后，同步到 Windows 部署副本并重启 Windows 桥接。
3. 新增选择器/iframe/等待结论写入 `onshape_browser_mode/selectors.py` 与
   `onshape_docs/experience/browser-automation.md`，不要在工具里散落字面量。
4. WSL 磁盘上不得残留 Windows 运行时对象（`user_data/`、`bridge/logs/`、
   `config/browser.local.toml`、`.venv` 内的 playwright）——均已 gitignore，
   开发自测后随手清理。
