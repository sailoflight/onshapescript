# 桥接目录：WSL 中继 + Windows 主体

> 通用 WIN-WSL 桥接架构协议见同目录 `ARCHITECTURE.md`（可复用于其他同架构 MCP）；
> 本文只写本项目的具体接线与维护规则。

## 职责边界（运行时）

| 对象 | 运行位置 | 角色 |
|---|---|---|
| `wsl_bridge_ctl.sh` | **WSL/Linux（DSH 里）** | WSL 一键控制 Windows bridge（`start` / `restart` / `status`）；经 WSL interop 调 Windows `wscript.exe`，只触发不运行主体 |
| `mcp_tcp_bridge.py` | **WSL/Linux（DSH 里）** | 唯一 WSL 运行时：stdio↔TCP 中继，连 `127.0.0.1:8766`，纯 stdlib |
| `bridge_server.py` | **Windows** | 常驻 TCP MCP 主体：`mcp_main.win.mcp.server.dispatch()` + 浏览器会话 |
| `mcp_main/win/mcp/server.py`（TOOLS/HANDLERS） | Windows 主体内 | MCP 工具注册与处理器的权威来源；数量见生成参考 |
| `mcp_main/win/mcp/runtime_prompt.py` | Windows 主体内 | canonical User/Operator runtime policy；initialize 原生返回 |
| `dsh/runtime-prompt-companion.js` | WSL DSH profile | 从 canonical source 生成；为不能投递 initialize instructions 的 DSH client 提供 namespaced prompt |
| `onshape_browser_mode/` + Playwright | Windows 主体内 | Edge 浏览器自动化 |
| `windows/*` | Windows 部署 | 无窗口启动/重启/自愈脚本 |

- WSL 仓库是**开发仓库**：开发完成后同步到 Windows 部署副本
  （`C:\MCP\onshapescript`，非 git 仓库）。
- WSL 只执行中继脚本；**不要**在 WSL 运行 `python -m mcp_main.win.mcp`（那是完整 stdio
  MCP 主体，浏览器工具需要 Windows 上的 Playwright/Edge）。
- 中继脚本必须保持**纯 stdlib**（`os/select/socket/sys`），不得引入
  Playwright 或任何 MCP 主体依赖。

## WSL DSH 接入（把中继 MCP 装给 WSL 里运行的 DSH）

DSH profile 必须同时安装工具 adapter 和 runtime-prompt companion。以
`dsh/cordis.patch.yml.example` 为唯一接线示例，将 `<repo>` 替换为 WSL
仓库绝对路径并合并到目标 profile 的 `cordis.patch.yml`。不要只安装
`@deepseek-ai/dsh-mcp-client`：当前 0.1.0-rc.8 只注册工具，不会把
`initialize.instructions` 放进模型 system prompt。

生成并检查 companion：

```bash
python3 mcp_main/wsl/dsh/build_runtime_prompt_companion.py
python3 mcp_main/wsl/dsh/build_runtime_prompt_companion.py --check
```

要点：

- DSH 的 MCP row 启动 `mcp_tcp_bridge.py 8766`，而不是直接起 MCP 包。
- companion row 加载生成的 `runtime-prompt-companion.js`；两行作为同一个 deployment generation 更新或回滚。
- 脚本路径与 `cwd` 使用 WSL 绝对路径；端口必须和 Windows Engine 一致。
- 中继不装 Playwright、不持浏览器、不缓存登录态；Windows 侧拥有 profile、凭据和 runtime state。
- Windows bridge 未启动时 relay 快速失败；按 Operator runbook 恢复，不能用 WSL body 替代。
- 工具可见但模型看不到 prompt revision 与两个生产角色时，client 不健康，停止产品使用。

## WSL 一键控制 Windows bridge

`wsl_bridge_ctl.sh` 在 WSL 里**触发**（不经 MCP、直接 WSL interop）Windows 侧的无窗口
启动/重启脚本，绝不把 `bridge_server.py` 跑在 WSL。用法与 taobao-mcp 同款：

```bash
mcp_main/wsl/wsl_bridge_ctl.sh start     # 无窗口启动 Windows bridge
mcp_main/wsl/wsl_bridge_ctl.sh restart   # 强杀浏览器+bridge 再启动（自愈）
mcp_main/wsl/wsl_bridge_ctl.sh status    # 检查 127.0.0.1:8766 是否可连（不调 Windows）
```

默认假设 Windows 部署副本在 `C:\MCP\onshapescript`、端口 `8766`；可用环境变量覆盖：

```bash
ONSHAPE_WIN_ROOT='C:\MCP\onshapescript' ONSHAPE_BRIDGE_PORT='8766' mcp_main/wsl/wsl_bridge_ctl.sh restart
```

`status` 用 `/dev/tcp` 检查回路端口，纯 WSL；`start`/`restart` 经
`/mnt/c/Windows/System32/wscript.exe` 调 `mcp_main\win\bridge\windows\*.vbs`。

## 维护规则

1. 改中继：只动 `mcp_tcp_bridge.py`，保持 stdlib-only；改完在 WSL 跑
   `python3 mcp_main/wsl/facade/mcp_tcp_bridge.py 8766` 冒烟。
2. 改 MCP 主体（`mcp_main/win/mcp/server.py`、`onshape_browser_mode/*`、`bridge_server.py`）：
   在 WSL 跑离线测试后，同步到 Windows 部署副本并重启 Windows 桥接。
3. 新增选择器/iframe/等待结论写入 `onshape_browser_mode/selectors.py` 与
   `onshape_docs/experience/browser-automation.md`，不要在工具里散落字面量。
4. WSL 磁盘上不得残留 Windows 运行时对象（`user_data/`、`bridge/logs/`、
   `config/browser.local.toml`、`.venv` 内的 playwright）——均已 gitignore，
   开发自测后随手清理。
