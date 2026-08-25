# WIN-WSL 桥接 MCP 架构模板

> 通用模板：适用于任何需要在 Windows 与 WSL 之间建立连接的 MCP 服务器。
> 治理包把本模板复制为 `windows-wsl-bridge` MCP 子类型规范；本文件同时保留 Onshape 项目的实例映射。
> 本模板规定双端职责、运行时生产角色提示与不变量，不规定内层必须采用哪一种传输方案。

## 1. 适用场景

- MCP 工具实现依赖 Windows 本机资源（可见 GUI、浏览器内核、驱动、注册表、仅 Windows 的 SDK/服务、持久登录态等）。
- MCP 客户端/agents 运行在 WSL/Linux，通过标准 MCP 协议调用工具。
- WSL 端保持极薄、无重依赖；Windows 端承载主体、原生资源、运行态和 canonical production-role prompt。

## 2. 角色与职责（核心契约）

| 端/组件 | 角色 | 职责 | 禁止 |
|---|---|---|---|
| **WSL 端** | **MCP Facade** | 对 agents 提供标准 MCP；转发请求以及完整 response/capabilities/instructions/tools/results/errors/notifications | 不实现工具业务、不装 Windows 专属依赖、不持有 Windows 状态、不改写角色提示 |
| **Windows 端** | **MCP Engine** | 实现初始化、运行时角色提示、工具和 handlers；持有 Windows 资源、会话、凭据和运行态 | 不依赖 WSL 仓库根指令提供生产提示，不暴露内层服务到公网 |
| **客户端 adapter** | **MCP 消费和模型投递层** | 注册工具，并把受信 runtime instructions 投递到模型提示 | 不得只注册 tools 而丢 instructions；不得用 MCP 简介/tool description 代替角色提示 |
| **Operator 集成** | **安装、健康与恢复层** | 安装 adapter、验证提示投递、观察、重启、恢复和回滚 | 不因运维身份获得产品业务或云端 mutation authority |

一句话：**WSL 保证客户端看到完整 MCP，Windows 保证工具与提示属于真实部署版本，客户端保证模型实际收到提示。**

## 3. 数据方案（自由选择，双端协商）

- 对外（agents ↔ WSL）：固定为 MCP 协议。
- 对内（WSL ↔ Windows）：项目可选 loopback TCP、Named Pipe、本地 HTTP/WebSocket、共享文件/事件或其他本地方案。
- 内层通道必须仅本机可达、可重连，并在需要时有握手/认证。
- 内层传输不得丢失、截断或自行解释 initialize response，尤其是 capabilities 和 instructions。

本项目使用 WSL2 镜像网络共享的 loopback TCP `127.0.0.1:8766`。

## 4. 双生产角色运行时提示（强制）

MCP Engine 必须提供一段有界、无秘密、带 revision 的 runtime prompt，同时包含 `Production / User` 和 `Production / Operator`。它是客户端连接 MCP 后给模型执行的操作提示，**不是 MCP 产品简介、README、工具清单、开发 AGENTS 或部署广告**。

提示至少包含：

1. Role router：公共能力/业务结果 -> User；安装、配置、可用性恢复、观察、备份/恢复、回滚 -> Operator；实质歧义先结构化询问。
2. User contract：只使用公开 capabilities/runtime schemas；优先最低成本和只读/dry-run；mutation 遵守 confirmation；不自行获取凭据、真实数据、额度、费用或破坏权限；runtime/deployment failure 转 Operator，不读源码/DSH 配置自行扩权。
3. Operator contract：从只读健康证据开始；使用匹配环境的 runbook；生产动作明确环境、身份、影响、备份/回滚、停止条件和批准；不以 Operator 身份执行产品业务或直接改源码。
4. Transition/authority：角色名不授予凭据、真实数据、生产写入、重启、费用或不可逆权限；转换显式且不合并权限。

动态工具名、参数、版本、端口、环境状态和完整清单属于 tools/schema/state/generated authorities，不复制进提示。

## 5. 提示权威、转发和客户端投递

Windows Engine 拥有与已部署 handlers 同版本的 canonical prompt，并通过 MCP initialize result 返回，标准字段为 `initialize.instructions`。WSL Facade 原样转发，不能另写本地提示或替换为 MCP 简介。

每个受支持客户端必须执行：

```text
initialize
  -> receive dual-production-role runtime prompt
  -> register/atomically replace namespaced model-prompt section
  -> expose tools/schema
  -> first task/tool decision
```

仅 `tools/list -> register tools` 不合格。客户端不能消费 MCP instructions 时，安装必须提供从同一 canonical source/revision 生成的 companion prompt；禁止手工复制客户端变体。compatibility matrix 记录每个 client 的 `native instructions | generated companion` 投递模式并做外部环境实测。

提示只对显式受信 MCP 安装获得 system/context authority，并且 capability-scoped，不控制无关聊天或仓库任务。reconnect/reinitialize 原子替换旧 revision，不重复累积；最终 dispose 删除对应 namespaced section。工具 generation 与 prompt revision 不得静默错配。

## 6. 硬约束（不变量）

1. agents 看到的是完整 MCP，内层传输对客户端透明。
2. Production role prompt 不依赖预读取项目 `AGENTS.md`；其他项目、空目录和纯聊天环境也能收到。
3. WSL Facade 零/最小依赖，不持有 Windows 对象、凭据、profile、日志或运行态。
4. Windows Engine 拥有持久会话、凭据、GUI 资源和 canonical prompt；WSL/client reconnect 不破坏它们。
5. 一个持久资源同一时刻只有一个 owner，除非有已验证锁/隔离。
6. 内层通信 local-only，默认不监听公网。
7. Windows Engine 在具体执行路径懒加载 GUI/内核重依赖。
8. 开发在 WSL，部署和运行在 Windows；同步保留 ignored 配置、凭据、profile、logs 和 state。
9. protocol stdout 只有 MCP；诊断进入 stderr 或 Engine log。
10. prompt/schema/handler 属于同一可验证部署 generation。

## 7. 示例实例化（本项目：Onshape 浏览器自动化 MCP）

| 模板角色 | 本项目实体 |
|---|---|
| WSL Facade | `mcp_main/bridge/mcp_tcp_bridge.py`（stdio ↔ TCP，纯 stdlib） |
| 内层数据方案 | loopback TCP `127.0.0.1:8766` |
| Windows Engine | `mcp_main/bridge/bridge_server.py`（常驻进程内 dispatch） |
| 工具本体 | `mcp_main/server.py` 的 `TOOLS`/`HANDLERS` |
| Windows 专属资源 | Edge + Playwright + `onshape_browser_mode/user_data/onshape_profile` |
| Canonical production prompt | `mcp_main/runtime_prompt.py`; revision combines `SERVER_VERSION` with `production-roles-v1` |
| Initialize implementation | `mcp_main/server.py::dispatch` returns the canonical prompt |
| DSH Web adapter | `@deepseek-ai/dsh-mcp-client` for tools plus generated `mcp_main/bridge/dsh/runtime-prompt-companion.js` for model-visible policy |
| Operator runbook | `docs/operations/MCP_RUNBOOK.md` and `mcp_main/bridge/windows/README.md` |
| Verification | MCP protocol/runtime-prompt tests, Windows bridge tests, and `docs/verification/MCP_CLIENT_COMPATIBILITY.md` external-cwd evidence |

Current architecture status: bridge/tool path and canonical prompt are
implemented. Raw stdio/WSL clients use native initialization instructions; DSH
0.1.0-rc.8 uses the generated companion. Repository compatibility is verified,
while installation in any specific production DSH profile remains Operator
runtime state.

## 8. 验收检查清单（通用）

- [ ] WSL Facade initialize/tools/list/tools/call 通过 Windows Engine 正常工作。
- [ ] Engine initialize response 包含当前 revision 的双生产角色提示。
- [ ] Facade byte-faithful 或按明确 canonical encoding 转发提示。
- [ ] 每个支持客户端在第一次模型工具判断前投递提示；只显示 tools 丢提示必须失败。
- [ ] 无项目 AGENTS 的外部 cwd/chat 仍可见 User 与 Operator 契约。
- [ ] User availability success 后停止配置/源码调查；failure 转 Operator。
- [ ] Operator recovery 不获得产品 mutation authority。
- [ ] reconnect 不重复 prompt，rollback 后 prompt/schema/handler revision 一致。
- [ ] WSL 无 Windows 重依赖、凭据、browser profile、runtime log/state。
- [ ] 内层通道 local-only，持久资源保持 single owner。

## 9. 维护规则

- 改 Facade：保持最小依赖，验证完整 initialize 转发和本地冒烟。
- 改 Engine/tool/runtime prompt：离线测试 -> 同步 Windows deployment -> 单次重启 -> 验证工具与提示 revision。
- 改 client adapter：验证 tool generation 与 namespaced prompt generation 同步 register/replace/dispose。
- 改端口、握手或提示 envelope：同步架构、compatibility matrix、安装配置和 Operator runbook。
- 具体 selector、session、iframe 和产品流程进入项目经验/模块文档，不在本模板展开。
