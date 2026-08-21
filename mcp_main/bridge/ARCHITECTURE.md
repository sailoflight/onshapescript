# WIN-WSL 桥接 MCP 架构模板

> 通用模板：适用于任何需要在 Windows 与 WSL 之间建立连接的 MCP 服务器。
> 本模板只规定**两端的职责与不变量**，不规定两端之间必须用哪种数据格式/传输方案。
> 双端可根据项目情况选择最佳数据方案——唯一硬要求是：**WSL 端对 agents 呈现的必须是 MCP**。

## 1. 适用场景

- MCP 的工具实现必须依赖 **Windows 本机资源**（可见 GUI、浏览器内核、驱动、注册表、
  仅 Windows 的 SDK/服务、持久登录态等）。
- MCP 的客户端/agents 运行在 **WSL/Linux**，通过标准 MCP 协议调用工具。
- 目标：WSL 端保持极薄、无重依赖；Windows 端承载主体与资源。

## 2. 角色与职责（核心契约）

| 端 | 角色 | 职责 | 禁止 |
|---|---|---|---|
| **WSL 端** | **MCP 门面（Facade）** | 对 agents 提供**标准 MCP 接口**（stdio，newline-delimited JSON-RPC）；把请求转发给 Windows；转发响应给客户端 | 不实现工具业务、不装 Windows 专属依赖、不持有 Windows 资源/会话状态 |
| **Windows 端** | **MCP 主体（Engine）** | 实现全部工具本体；持有 Windows 专属资源（GUI/内核/持久会话/凭据）；向 WSL 门面提供服务 | 不参与开发仓库演化；只承载部署产物与运行态 |

一句话：**WSL 端保证“看到的是 MCP”，Windows 端保证“工具真正能跑”。**

## 3. 数据方案（自由选择，双端协商）

- 对外（agents ↔ WSL 端）：**固定为 MCP 协议**（stdio JSON-RPC）。这是唯一不可变的部分。
- 对内（WSL 端 ↔ Windows 端）：**项目自选最佳方案**，模板不强制。可选：
  - loopback TCP（WSL2 镜像网络共享 `127.0.0.1`，本项目采用）；
  - Windows 命名管道（Named Pipe）；
  - 本地 HTTP / WebSocket；
  - 共享文件 + 事件 / 共享内存等。
- 内层方案只需满足：**仅本机可达、连接可重入（客户端重连不丢会话）、必要时有握手/认证**。

## 4. 硬约束（不变量）

1. **agents 看到的就是 MCP**：WSL 端必须是合法的 stdio MCP server；内层用什么传输与客户端无关。
2. **WSL 端零/最小依赖**：理想为纯标准库；任何 Windows 专属对象（内核、驱动、会话、凭据）
   都不应出现在 WSL 端运行时。
3. **Windows 端拥有状态**：持久会话、凭据、GUI 资源全部归 Windows 端；WSL 门面重启/客户端
   重连不得破坏 Windows 端状态。
4. **共享资源单属主**：一个持久资源（如一个浏览器 profile / 一个内核实例）同一时刻只能被
   一个进程持有；多实例需显式锁。
5. **仅本机通信**：内层通道不监听公网，默认 loopback/本机。
6. **主体懒加载重依赖**：Windows 主体在顶层导入时不得强拉 GUI/内核依赖；只在具体工具
   执行路径内加载，保证错误边界清晰。
7. **开发在 WSL，运行在 Windows**：WSL 是开发仓库与离线测试场所；Windows 是部署副本与运行场所。

## 5. 示例实例化（本项目：Onshape 浏览器自动化 MCP）

把通用模板映射到本项目：

| 模板角色 | 本项目实体 |
|---|---|
| WSL 门面 | `mcp_main/bridge/mcp_tcp_bridge.py`（stdio↔TCP 中继，纯标准库） |
| 内层数据方案 | loopback TCP `127.0.0.1:8766`（WSL2 镜像网络） |
| Windows 主体 | `mcp_main/bridge/bridge_server.py`（常驻进程内 dispatch） |
| 工具本体 | `mcp_main/server.py` 的 TOOLS/HANDLERS |
| Windows 专属资源 | Edge + Playwright + `onshape_browser_mode/user_data/onshape_profile`（持久登录态） |

- WSL DSH 接入配置见 `mcp_main/bridge/README.md`；Windows 部署见
  `mcp_main/bridge/windows/README.md`。
- 本项目选择 TCP 而非命名管道，是因为 WSL2 与 Windows 通过镜像网络共享 `127.0.0.1`，
  且中继只需标准库 socket。若换命名管道/HTTP，只需替换 WSL 门面与 Windows 主体的
  传输层，其余职责划分不变。

## 6. 验收检查清单（通用）

- [ ] WSL 端能作为 stdio MCP server 被 agents 启动，`tools/list` 正常。
- [ ] WSL 端不引入 Windows 专属依赖（如 `import <win-only>` 报 `ModuleNotFoundError`）。
- [ ] 主体顶层无重依赖导入（`grep -nE "^(import|from) <heavy>" <body>.py` 为空）。
- [ ] Windows 主体重启/客户端重连后，Windows 端持久状态保持（不因重连丢失）。
- [ ] 内层通道仅本机可达，不暴露公网。
- [ ] WSL 磁盘无 Windows 运行时对象（会话目录、日志、本地配置、venv 内重依赖）。

## 7. 维护规则

- 改 WSL 门面：保持最小依赖，改完本地冒烟。
- 改 Windows 主体：离线测试 → 同步 Windows 部署副本 → 重启主体。
- 双端契约变更（端口/管道名/握手协议）必须同步更新两侧文档与配置。
- 本文档是**架构模板**；具体选择器/会话/iframe 等行为细节进各项目经验文档，不在模板里展开。
