# 压缩视图与空闲会话检测器的实机验收（2026-09-21）

## 1. 这次要验证什么

三件事，全部 0 REST 配额、0 云端数据变更：

1. **Windows 那台部署确实切到了 `gateway` 压缩视图**，且不是「只能检索」——被展示的
   16 个入口覆盖全部类别；
2. **`mcp_tool_invoke` 能把一次调用送到未展示的注册名**。这曾是真实客户端的硬限制：
   不在 `tools/list` 里的名字会得到 `unknown tool`，而服务端照常 dispatch；
3. **`browser_session action=health` 在桥重启后能不能自己发现「页面看着是开的、服务端
   会话已过期」**——用户要求的「提前准备一个检测器」。

## 2. 环境与身份

- 部署：`/mnt/c/MCP/onshapescript`，deployment id `20260921T120000Z-invoke`，
  `shippedFiles: 16 / changed: 16 / unmatched: 0`（`verify` 报 `mismatched: []`）。
- 宿主开关（不在仓库、不随部署下发）：
  `mcp_main/win/mcp/config/tool_views.local.toml` → `[exposure] mode = "gateway"`。
- 桥：`bridge_control(action="restart", id="onshape", expectedGeneration=90)`
  → `ownedGeneration: 91`，`toolsListChangedNotifiedClients: 5`，`force-kill: not-needed`。
  重启后连接需 `bridge_library action="expand"`（`toolCount: 16`，`catalogStatus: verified`）。
- 目标文档（会话恢复用）：`Gridfinity 2x2 baseplate | GF 4U 盒子`，
  `1ef2be8f3d45e6f996af24ab` / `bac7c0bf31912a956c44d15a` / `59f6cc99890dd2fea26d5471`。

## 3. 结果一：压缩视图可用，且不是「只能检索」

`mcp_tool_invoke` 之前被 16 个展示入口取代的是 15 个；补齐后 gateway = 核心 3
（`mcp_tool_catalog`、`mcp_tool_view`、`mcp_tool_invoke`）+ 策展 13，覆盖
control / browser / rest / rest_reference / featurescript / documentation 六个类别。
离线量测（`dev/tools/context_cost.py`，写入
`onshape_docs/verification/context-cost-surfaces-2026-09-21.json`）：

| 视图 | 工具数 | 字符 | 估算 token |
|---|---|---|---|
| `static`（完整 registry） | 111 | 226,845 | 56,769 |
| `semantic`（默认） | 77 | 166,827 | 41,748 |
| `gateway` | 16 | 43,102 | 10,795 |

即 gateway 比完整 registry 小 **5.3x**、比默认视图小 **3.9x**。策展入口存在的原因就是
**检索不便宜**：三结果 `search` ≈ 6.8 kB、一次建模 `describe` ≈ 10.5 kB，所以
「只列 search」会让最常见的建模任务先付一次没必要的检索。

## 4. 结果二：`mcp_tool_invoke` 实机送达未展示的名字

实机调用（同一连接、gateway 视图）：

```
mcp_tool_invoke { "name": "docs_list", "arguments": {} }
```

返回 `invokedTool: "docs_list"` 与 `docs_list` 自己的完整答案（`count: 30`、
六类 30 页、每页小节列表）。`docs_list` **不在**被展示的 16 个名字里——这正是
2026-09-21 早些时候真实客户端报 `unknown tool "mcp__onshape__docs_list"` 的那个名字。

边界与保证（离线测试 `dev/tests/test_tool_gateway_view.py::InvokeToolTest` 逐条钉住）：

- 目标是**同一个 `HANDLERS` 条目**，`tool_result` 的响应压缩也在同一条路径上跑；
- `confirm_mutation`、`dry_run`、quota、pacing、验收门全部照常回答——实测
  `browser_insert_custom_feature` 不带 `confirm_mutation` 时**照样被拒**，
  `browser_delete_feature` 的 `dry_run` 仍是 `estimatedApiRequests: 0` 的预览；
- 连接级工具（`mcp_tool_view`、`mcp_tool_catalog`、它自己）被**拒绝**而不是递归；
- 未知名字报 `Unknown tool: …` 并指向 `mcp_tool_catalog`；
- 该入口在**每种展示模式**都被列出（语义视图 76 → 77 个工具，+2,207 字符）：对拒绝
  未展示名的客户端来说，藏起来的逃生门等于没有门。

## 5. 结果三：检测器在真机上**先判对、再被自己的建议打脸**

桥重启后第一次探针（0 配额、只读、不启动浏览器、不点击）：

```json
{"verdict": "browser_not_running", "recommendedAction": "browser_session action=login"}
```

`action=login` 恢复页面（「Browser session is already logged in (restored Onshape
page was kept)」），再探：

```json
{"verdict": "session_timeout_dialog",
 "recommendedAction": "browser_session action=reconnect",
 "probe": {"responded": true, "roundTripMs": 44, "timeoutDialogPresent": true,
           "timeoutDialogLinkText": "",
           "timeoutDialogMessage": "未连接 Onshape。 您的文档已保存。 正在尝试重新连接…",
           "documentShellReady": true, "title": "Gridfinity 2x2 baseplate | GF 4U 盒子"}}
```

按建议执行 `action=reconnect`：**30 秒点击超时**，元素
`.alert-link.osx-message-bubble-link` 在 DOM 里但不可见、文本为空。紧接着再探一次：

```json
{"verdict": "ok", "recommendedAction": "none",
 "probe": {"responded": true, "roundTripMs": 4, "timeoutDialogPresent": false,
           "documentShellReady": true}}
```

**判决对了一半，建议是错的**：那个对话框有两种状态，而分不清就会推荐一个物理上做不到
的动作。修正（离线 927 测试通过，0 REST）：

| 状态 | 判据 | 动作 |
|---|---|---|
| 链接可点 | 有布局盒（`getClientRects().length > 0`）且 `linkText` 非空 | 点击；返回 `mode: "click"` |
| 自动重连中 | 链接在 DOM 但不可见/无文本 | **不点击**，有界等待（15 s）它自己消失；返回 `mode: "automatic"`；未清掉才退 `action=reload` |

探针新增 `timeoutDialogActionable`；不可点时 `recommendedAction` 改成
`browser_session action=health`（复探），点击超时也从默认 30 s 收到 5 s。
可复用教训见 `onshape_docs/experience/browser-modeling.md` §29.1。

## 6. 边界（本页不声明的东西）

- 不声明 Onshape 会话过期的**时长**：本页只记录两种状态与正确动作，没有测出间隔。
- 不声明 token 真实值：上表是**估算**（4 字符/token、CJK 1 字/token），宿主上没有
  tokenizer 可校准。
- `mcp_tool_invoke` 只保证「送达同一个 handler」，不保证目标工具在语义上适合被调用。
- 会话恢复后未再执行任何建模或写操作；本轮 0 次真实 REST 调用、0 次云端变更。

## 7. 复现

```bash
# 离线：量测 + 全部测试
python3 dev/tools/context_cost.py > onshape_docs/verification/context-cost-surfaces-2026-09-21.json
PYTHONPATH=temp/browser-common-site python3 -m unittest discover -s dev/tests

# 部署（Windows 宿主）
python3 temp/deploy_refresh/deploy.py plan  --deployment-id <id>
python3 temp/deploy_refresh/deploy.py apply --deployment-id <id>
python3 temp/deploy_refresh/deploy.py verify --deployment-id <id>   # mismatched: []

# 实机（0 REST）
#   bridge_control restart → bridge_library expand
#   mcp_tool_invoke {name: "docs_list"}
#   browser_session action=health   （必要时 login → 再 health）
```
