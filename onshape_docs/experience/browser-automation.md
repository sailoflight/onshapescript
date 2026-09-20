# 浏览器自动化使用经验（Onshape Windows 宿主）

本文档是 2026-08-20 起对 Onshape 浏览器自动化探索的**使用经验**沉淀，供后续
开发 page objects / selector 映射 / 自动化脚本时直接复用。所有结论都来自
真实 Edge（channel=msedge）+ 持久化 profile 的实测，0 次 Onshape API 调用。

## 1. 运行模型

- 普通 MCP 与浏览器运行在同一宿主（当前实测宿主为 **Windows**）；跨宿主客户端通过独立安装的 `win-wsl-mcp-bridge` 连接。
- 项目源码入口是 `python -m mcp_main.win.mcp`。共享桥若需要跨客户端重连保持会话，必须在其自身生命周期契约中保持同一 MCP 进程并禁止 profile 多 owner；本仓库不再实现 relay/listener。
- 即使跨客户端 transport 已提供单 backend/profile owner、多客户端 JSON-RPC 路由与单次
  `tools/call` 串行，Onshape 仍没有 document lease 或多调用工作流原子性。客户端共享
  登录态、当前页面、active Studio 和 backend 内存；`A1, B1, A2` 可以在请求边界交错。
- 当前生产边界是多客户端安全只读 + 单一修改 agent。修改 agent 从首次目标定位到最终
  验收、共享 target-state 同步和 browser release 持续独占；其他 agent 不得依赖当前页
  或配置默认 target。`client_lease_busy` 只能等待或退出。
- **单工作页铁律**：`session.start()` 每次只保留一个工作页，其余标签全关
  （`_enforce_single_working_page`）。
- agent 完成浏览器工作后应在 finally 风格的清理中调用
  `browser_session(action="release")`，除非明确需要继续使用同一浏览器。该动作不启动
  浏览器，只关闭当前 MCP 进程的 context/Playwright 并复位状态；不能释放另一进程的
  owner，重复调用安全。
- 关闭方式决定登录态：**强杀进程保留登录，优雅关闭可能需要重新确认登录**。Onshape 无“保持登录”。

## 2. 登录态恢复经验

- Onshape WEB 端：浏览器一关立即登出，没有“保持登录”选项。
- 恢复登录的两个条件：profile 里的 **cookie** + **上次的入口 URL**。
  - 入口 URL 例如 `https://cad.onshape.com/documents?resourceType=resourceuserowner&nodeId=<id>`
  - 由 `onshape_browser_mode/config/browser-state.json` 的 `lastAppUrl` 持久化，`status()` 每次见到已登录页自动落盘。
- 判定“已登录”要等 **SPA 路由稳定**：`domcontentloaded` 后 URL 可能是短暂的 documents，
  4 秒后前端路由会把未登录会话重定向到 `/signin`。`open_login_page()` 已按最终 URL 判定。
- 强杀 vs 优雅关闭的差异是真实存在的：强杀不给页面执行登出逻辑的机会，会话文件保留
  documents URL；优雅关闭会把页面写回 signin。

## 3. 浏览器工具（browser_*）

| 工具 | 用途 | 关键参数 |
|---|---|---|
| `browser_session` | 登录态/页面状态/释放当前进程 owner | `action=status|login|release` |
| `browser_watch` | 录制人工操作（URL/网络/对话框） | `action=start|stop|report` |
| `browser_inspect` | 可见可交互元素清单 | `max_elements` |
| `browser_scroll` | 滚动窗口或指定容器 | `direction`, `amount`, `selector` |
| `browser_click` | 点击元素（实际点击需 `confirm_mutation=true`；`dry_run` 只检查目标不点击） | `selector`/`text`, `index`, `dry_run`, `confirm_mutation` |
| `browser_eval` | 页面内 JS 求值（执行需 `confirm_mutation=true`；`dry_run` 只返回表达式元数据不执行） | `expression`, `arg`, `dry_run`, `confirm_mutation` |
| `browser_open_document` | 只读打开文档并解析 did/wid/eid | `document_name` |
| `browser_read_featurescript` | 只读读回 Ace 全文 + 页面 id 三元组 | — |
| `browser_deploy_featurescript` | **0 配额部署 FS**（写 Ace + 点提交，需确认） | `script`, `document_name`, `dry_run`, `confirm_mutation` |

所有工具 `network: "browser"`、`estimated_api_requests: 0`——不花 Onshape API 额度。
`browser_click` / `browser_eval` 现在标注为 `mutating`（可能触发云端 UI 变更）：真正执行
必须 `confirm_mutation=true`；`dry_run=true` 不产生点击/求值副作用，无需确认。
真实浏览器动作还受 `onshape_browser_mode/config/browser.toml` 的 `[pacing]` 约束：
默认最多 8 次/分钟，并在动作前随机等待 0.8–2 秒。新增工具或参数以
`docs_section(page="mcp-server")` 和 `tools/list` 为准，本页不承担完整注册表职责。

### 3.1 六级语义发现约定

六级语义只帮助发现和选型，不授予执行权限，也不要求每个工具必须标级：

- L1/L2 分别是通用浏览器原语和通用浏览器事务；
- L3 是不声明领域成功的 Onshape 准备、诊断或恢复交互；
- L4 是一个完整且已验证的 Onshape 事务或观察；
- L5 是多个独立 L4 组成的工作流；
- L6 是带最终验收、manifest 和 provenance 的独立成果；
- Project 是一个或多个 L6 的控制平面，不属于 L1-L6。

普通发现按 L5 workflow → L4 verified transaction/observation → L2 generic
transaction → L6 deliverable recipe 排序。这样先复用完成的多事务能力，只有明确需要
独立 artifact/manifest/retry 边界时才选择 L6。L1/L3 为减少
普通上下文默认不暴露，但并非隐藏知识：开发、异常恢复或人工辅助需要时调用
`browser_discover_tools` 并显式传 `semantic_levels=["L1"]` 或
`semantic_levels=["L3"]`，再按返回的**精确注册名**直接调用（`mcp_tool_catalog`
同样返回精确名与完整 schema）；没有单独的 invocation gateway 需要绕，发现步骤也
不绕过确认、成本或 handler 验收。未分类工具继续有效并默认可见；`ONSHAPE_MCP_TOOL_EXPOSURE=static` 保留完整列表兼容模式。当前审阅
元数据和非阻断 lint 在
`onshape_browser_mode/semantics.py`。

### 3.2 连接级动态展示约定

`mcp_tool_view` 的 profile/semantic-level 只缩小当前连接返回的 `tools/list`，不修改
完整 registry，不拒绝已知工具名，也不改变确认、quota、pacing 或验收门。正确流程是：
Operator 以 `ONSHAPE_MCP_TOOL_EXPOSURE=dynamic` 启动；client 在 initialize 中确认
`tools.listChanged=true`；agent 先 `status`，再 `set`；client 收到
`notifications/tools/list_changed` 后重新请求并**替换** `tools/list`，不能在旧列表上追加。
`reset` 回到该连接启动时的 profile；重新连接创建独立的新 view。

窄化 browser semantic levels 时必须常驻 `browser_session` 和
`browser_discover_tools`，否则 agent 难以观察、继续发现或恢复视图；被合并吸收的
兼容名不常驻，只能按精确名调用。重复设置同一 view 不发 notification。客户端不支持 listChanged 时继续使用
固定 `semantic`/`profile` 或 discovery gateway，不要把“未展示”解释为“禁止”。

### 3.3 跨模块工具目录约定

`mcp_tool_catalog` 是 MCP capability 的统一 lookup-first 入口，不受当前 view 限制。
索引只在完整 registry 安装和 cost metadata 补全后构建一次；所有连接共享同一 immutable
index，仅 `visibleInCurrentView` 按连接计算。使用顺序固定为 `status` → bounded `search`
→ exact `describe` → normal call。search 默认 8、上限 12，描述截断且绝不含
`inputSchema`；只有 exact-name describe 返回完整 schema/cost/annotations。

自由文本只索引名称、描述、module 和 browser semantic name。profile/network/mutating/
semantic level 必须作为结构化过滤器，尤其不能把 profile 名加入全文 token，否则属于每个
profile 的控制工具会污染结果。客户端可用 SHA-256 fingerprint 缓存目录结果；fingerprint
变化时失效。目录命中、当前可见和可按已知名调用都只是发现事实，不是授权事实。

## 4. Onshape 页面结构实测

### 4.1 「我所有的文档」页（Documents）

- URL：`/documents?resourceType=resourceuserowner&nodeId=<id>`
- 文档列表是 **AG Grid**，滚动容器是 `.ag-body-viewport`（或
  `.ag-body-vertical-scroll-viewport`）；整个窗口 `scrollY` 恒为 0，别用 window 滚动。
- 左侧还有 `.os-document-list-grid-container`（可滚 200px 左右）。
- 稳定选择器：
  - 搜索：`#search-box`
  - 通知：`#user-notification-status`
  - 新建：`#create-new-type`（文本「创建」）
  - 文档行链接：`.document-list-item-name`、`.document-display-link`、`.os-document-display-name`
- 当前账号下文档（实测）：`初稿`、`Branch Cable Trophy Display - FeatureScript`、
  `无标题文档`×N、`IMG_20250409_084546.jpg`、`k37` 等。目标文档是
  **Branch Cable Trophy Display - FeatureScript**。

### 4.2 Part Studio / FeatureScript 页

- 点击文档名后进入：`/documents/<did>/w/<wid>/e/<eid>`。
- 顶部导航新增：`共享` 按钮（`.nav-share`）、`搜索工具… alt/⌥c`（`.command-search-trigger`）。
- 文档标签：`tab-list-item.os-tab-bar-tab`，标签名在 `.os-tab-name`。当前文档的标签：
  - `Branch cable trophy display`（FeatureScript，默认激活）
  - `Cable trophy model v1`（Part Studio）
  - `Cable trophy model validation`（Part Studio）
  - `FS live verification`、`instance 0*-*.fs` 等 FeatureScript 实例页
- FeatureScript 编辑器是 **Ace editor**：
  - 输入区 `textarea.ace_text-input`（aria「Cursor at row …」）
  - 折叠控件 `.ace_fold-widget`
  - **读全文方法**（0 配额；执行需 `confirm_mutation=true`）：`browser_eval` 跑
    `const el=document.querySelector('.ace_editor'); const ed=(el.env&&el.env.editor)||window.ace.edit(el); ed.getValue()`
    实测读到「Branch cable trophy display」全文 571 行 / 23875 字符，已存
    `dev/fixtures-capture/branch-cable-trophy-display.fs`。注意 DOM 渲染只含可见行，
    必须走 Ace API 才能拿全文。
- FeatureScript 工具栏（容器 `.os-feature-studio-main-menu-bar`，按钮 `.tool.is-activatable.is-button`）：
  - 撤消（disabled）、新特征、`Length parameter`、导入、**提交**（`.os-primary`，无改动时 disabled）、
    `Module outline`（`.top-level-symbols-button`，标签在 `.top-level-symbols-label`）、ref 前进/后退（disabled）
  - Ace `editor.session.getAnnotations()` 不是完整编译证据：实测当前 Feature Studio
    返回 `annotationCount:0`，但黄色 `.notice-pane-toggle-button` 同时显示 28 条
    FeatureScript 通知，包括 `precondition analysis failed`、变量未找到和 bounds
    类型错误。通知根为 `.notices-content`，每条表为
    `.feature-script-notice-table`，正文/行/列分别在 `.notice-location-message`、
    `.notice-location-line-number`、`.notice-location-column-number`，严重度为
    `.fs-notice-error|warning|info`。证据见 `dev/button-map/scan-fs-notices.json`。
  - L3 `browser_fs_read_notices` 在需要时展开通知面板、解析当前标签消息并恢复原状态；
    L4 `browser_get_fs_compile_status` 将通知与 Ace annotations 合并。通知指示器存在但
    无法读取时保守返回 `compiled:false`。部署只有在提交按钮从 enabled 变为 disabled、
    源码精确回读且综合编译证据无 blocking warning/error 时才返回 `deployed:true`。
  - Module outline 展开后使用 `.top-level-symbols-dropdown` / `.top-level-symbol-list` /
    `.top-level-symbol-item`；名称和图标分别是 `.top-level-symbol-name` 与
    `.top-level-symbol-icon`。实测 `C`、`ƒ`、`Φ` 分别表示 const、function、feature。
    `browser_get_fs_symbols` 保留 `displayName/rawIcon` 并返回归一化 `kind/name`；
    原始证据见 `dev/button-map/scan-fs-module-outline.json`。
  - Ace 右键菜单实测为 `粘贴` / `转至定义` / `插入代码段`；`插入代码段`
    直接修改源码，没有另开对话框。Ace 同时暴露 `fold` / `unfold` /
    `toggleFoldWidget` 命令，`.ace_fold-widget` 的开放状态类为
    `ace_start ace_open`。探测插入已立即撤消，浏览器源码长度和 FNV-1a
    与 fixture 完全一致；证据在 `dev/button-map/scan-fs-editor.json`。
- FeatureScript 悬浮文档：`.os-feature-script-doc-popup-layer`（当前显示
  `LengthBoundSpec type A spec to be used with the isLength pre...`）。
- 监控/配置 split control：可见根为 `.watch-part-studio-menu`，下拉箭头是
  `.os-toolgroup-open-button`，当前目标在 `.os-tool-command-name`；下拉选项才使用
  `.os-tool-dropdown-content .os-menu-tool`（文本形如 `监控 PS-PartA-wall` /
  `配置文件 PS-PartA-wall`）。

### 4.3 会话超时弹窗（重要）

- 长时间不操作后出现，文本：「您的 Onshape 会话已超时。 您的文档已保存。 单击此处重新连接。」
- 重连链接：`a.alert-link.osx-message-bubble-link`（文本「单击此处重新连接。」）
- 容器：`.osx-message`；关闭按钮：`.osx-close`
- `browser_session(action="reconnect")` 会检测并点击该链接恢复会话（旧的
  `browser_reconnect` 名字仍可用，但只是兼容包装）；`browser_open_document` /
  `browser_read_featurescript` / `browser_deploy_featurescript` 在执行前自动重连。
- 实测：点击后弹窗消失，页面回到原文档 URL。

### 4.4 Part Studio 页与「添加自定义特征」对话框

- Part Studio 标签 URL 的 elementId 与 FS 标签不同（`0c7862642d02c53c3dd7cd79`）。
- 特征树：`.features-title`（「特征 (5)」）、`.os-list-item`；
  自定义特征 `.os-list-item.ns-user-feature`（如 `Bc Branch cable trophy display`），
  默认几何图元 `.os-list-item.ns-default-feature`。
- 零件列表：`.part-list-container`（`零件数 (132) base ...`）。
- **验收需要三个信号同时成立**，缺一不可：特征树出现该自定义特征的
  `.os-list-item.ns-user-feature` 行；该行的 class 与文本不含
  `not-computed` / `error` / `未计算` / `错误`；`零件数 > 0`。
  `browser-modeling.md` §6 明确记录「`not-computed` 行仍然是一行」，所以只凭行存在，
  会在其他特征已提供几何时报出假成功。`browser_build_part` /
  `browser_deploy_and_apply_featurescript` 把三者分开报告（`featurePresent`、
  `featureComputed`、`featureError`），未通过时给出 `reason`；`errored` 是 UI 信号
  而不是领域结论，重新生成期间也可能短暂出现，因此只报告、不重试接受按钮
  （第二次点击会再加一个特征，而不是修好这一个）。
- **第四个信号：工作区是否真的收下了这个特征（2026-09-20 实测）**。上面三个信号
  全部成立，仍可能只是**工作台本地状态**：浏览器插入的自定义特征在页面
  **重新加载之前不会进入工作区**，此时 REST `GET .../features` 对同一 element
  返回空列表（同一分钟内重复读取仍为空，所以不是读取缓存；对照实验用 REST
  `addPartStudioFeature` 添加的特征立刻可见）。因此
  `actions.insert_custom_feature` 在行与零件出现之后**再重载一次页面**，要求该行
  在重载后仍然存在，才把 `inserted` 置为 true；结果里的 `commit`
  （`verified` / `committed` / `reload` / `panel`）单独记录这次确认，重载失败或
  面板读不到时如实报 `verified: false` 且不假装成功。证据见
  `onshape_docs/verification/browser-rest-handoff-2026-09-20.json`。
  两个等待的预算按 element 里的**自定义特征数**放大（`PARTSTUDIO_RELOAD_WAIT` /
  `PARTSTUDIO_REGENERATE_WAIT`：30 s 底 + 每特征 8 s / 2 s，各自有上限），因为
  重载会重新计算**每一个**特征：5 个特征的 Part Studio 实测生存等待用掉
  18 431 ms / 固定 30 000 ms，固定预算会随文档增长而变薄，并且只会往"已提交却
  报未提交"的方向失败。读不到特征数时退回原固定预算（不会变短）。
- **切标签后先等面板渲染，再读基线（2026-09-20 实测）**。从 Feature Studio 切到
  Part Studio 后立刻读特征树，会读到**空面板**：实测在已有 8 个自定义特征的文档上
  `budgets.customFeaturesRead: 0`，于是 `minimum = 0 + 1 = 1`，恰好被屏幕上一个
  旧行满足 —— 一次静默的假通过。所以 `insert_custom_feature` 在切标签后先等
  「面板出现至少 1 行」（`.features-title` / `.os-list-item`，30 s）再等
  「工作区自定义特征按钮可见」（`PS_WORKSPACE_CUSTOM_FEATURE_BTN`，30 s），
  两者都记进结果的 `panelReady` / `toolbarReady`；没有切标签时不花这两个等待。
  另外**没有任何工具能"切换当前标签"**：只有带标签参数的复合事务会切
  （`browser_insert_custom_feature(part_studio_tab=)`、
  `browser_deploy_and_apply_featurescript(feature_studio_tab=, part_studio_tab=)`、
  `browser_export_step` 等），而 `browser_get_partstudio_features` 只读**当前屏幕**
  那一个标签。
  `browser_create_tab(tab_type="Feature Studio")` 是让起点落在 Feature Studio 的可见
  手段（它创建的标签会立即成为当前标签）；2026-09-20 用它造起点，才让"从 Feature
  Studio 切到 Part Studio"这个前置条件可复现。只点当前标签等于没切，那两个等待也不会
  被花掉。
- **接受按钮不能"点完就数"（2026-09-20 实测）**。`browser_edit_feature_parameters`
  第一版点完 ✓ 只固定 `wait_for_timeout(500)` 再数输入框，成功应用的那次却报
  `accepted: false` / `parametersApplied: false`；第二次调用读到的 `before`
  已经是新值。改成有界条件等待
  （`page.wait_for_function('(selector) => document.querySelector(selector) === null', arg=PS_FEATURE_DIALOG, timeout=60_000)`）
  后同一操作报 `parametersApplied: true` / `accepted: true` / `regenerationOk: true`
  / `persistenceOk: true`。**"对话框关闭"是这里唯一可读的完成信号**，不是经过多少毫秒
  ——但这条信号只在一半情况下可靠，见下一段 2026-09-20 第四轮的实测修正：
  accept **真改了参数**时它 95 s 仍未出现，而提交早已落库。
- **"对话框关闭"不是"参数已改"的完成信号（2026-09-20 第四轮实测，修正上一条）**。
  同一元素、同一特征、同一代码路径，只改"accept 是否真的改变参数"这一个变量：

  | accept | 对话框 `before` → `after` | 关闭条件 |
  |---|---|---|
  | 真改参数 | `10 mm` → `12 mm` | **95 s 仍未满足**（25+25+45 s） |
  | 空操作 | `12 mm` → `12 mm` | **满足，5 ms** |
  | 真改参数 | `12 mm` → `10 mm` | **60 s 仍未满足**（20+40 s） |
  | 空操作（复位） | `10 mm` → `10 mm` | **满足，4 ms** |

  这四次 accept **全部提交成功**，而且证据不依赖对话框：每次真改之后用一次有界页面
  重载丢掉那个还开着的面板，再从**全新加载的页面**打开对话框，`before` 读到的就是**新值**
  （第一次后 12 mm，第三次后 10 mm）。重载只丢客户端 UI 状态，不会撤销服务端提交。
  操作员在同一 95 s 时间窗内（15:18:30 +0800）看到的面板也确实是开着的、外观正常
  （标题 `Spiral ridge 1`、`Base radius 12 mm`、绿色 ✓、红色 ✗，行选中，无转圈无报错）。
  **所以"面板移除"对真改参数这一类编辑不是完成信号**；它瞬间满足空操作、对真改长时间
  不满足，而两种情况下的提交都已完成。要在这类编辑上拿到判决，只能走"重载 → 重新打开
  并读回值"（本轮实测可行，且读回值与请求值逐字相符），不能等面板消失。
- **第二段自己带恢复路径，判据按"有没有恢复过"分级（2026-09-20 落地）**。
  `browser_verify_feature_parameters` 不再用单一长超时去等面板关闭：它先做一次
  **短探测**（`dialog_timeout_ms`，默认 3 s），面板已关就直接读回；面板还开着且
  `allow_reload=True`（默认）就**只做一次有界重载**，然后在全新页面上重新探测、
  重新打开特征行读回值，结果里带 `recoveredBy: "page_reload"` 与 `recovery` 字段。
  判决分级是硬要求：**恢复重载之后仍读不到**才允许 `parametersApplied: null` +
  `retryVerify: true`（并明说"raced the commit"），而**没有**走过恢复路径就长时间
  读不到时给的是确定性的 `parametersApplied: false`，不是 `null`。理由很实际：
  一类"我没有证据"必须能被上层重试，另一类"证据显示没生效"不能靠重试蒙过去；
  把两者都写成 `null` 就是让调用方无法区分。行状态读回显示特征没有重新生成干净时，
  同样给确定性的 `false`（此前那个分支会漏成空洞的 `null`）。
  注意这与"重载 ≠ 回滚"这条并存：重载丢掉的是客户端 UI 状态，不是服务端提交，
  所以重载后读回的新值恰恰是提交证据，而不是把编辑抹掉。
- **要知道特征当前参数值，必须用只读探针，不能"填一个值试试"（2026-09-20 落地）**。
  新增 `browser_read_feature_parameters(feature_name, allow_reload=False)`：双击特征行
  打开对话框、读值、**无条件按 Escape 取消**，全程不填不改，所以它是
  `mutating=False`。返回 `read` / `parameters` / `parameterCount` / `featureRow`，
  读不到时给 `retryable` 与原因。它存在的直接原因是一个被实现挡住的取巧：
  想用 `browser_edit_feature_parameters(parameters={})` 做"零改动读回"是不可能的，
  handler 会以 `ValueError("parameters must be a non-empty object")` 拒绝——**这个拒绝
  是对的**，保留它，不要为了省一个工具而放宽。默认 `allow_reload=False` 也是刻意的：
  第一段刚点完 ✓ 时，一次重载会把面板扔掉并白白多花一次页面加载；只有第二段在
  面板卡住时才值得付这个代价（所以 verify 的默认是 `True`，read 的默认是 `False`）。
- **重载之后的就绪判据必须是"你马上要读的那一行"，不能是"页面上有任意列表项"
  （2026-09-20 真机实测，随后修复）**。恢复重载后页面是**分阶段渲染**的，两条路径都栽在
  这一点上：
  - `verify_feature_parameters` 的恢复分支在 `reload_page()` 之后**没有任何等待**就枚举行，
    整个恢复段 151 ms 结束、枚举到 0 行，返回 `parametersApplied: null` +
    `retryVerify: true`——**没有撒谎，但白跑一次调用**（下一次调用才读到已提交的 12 mm）。
    同一次返回里 `tabs: []`、`hasDocumentTabsToolButton: false` 就是页面还没加载完的证据。
  - 只读探针那条路径**有**等待也不够：`wait_for_panel_rows` 数的是 `.os-list-item`
    （`selectors.py:69` 的 `PARTSTUDIO_FEATURE_ITEM`），零件表行、标签条、加载骨架都能满足
    它，所以实测 `waited: true` / `2736 ms`，而同一刻枚举到 **0 个**自定义特征行。
  - 修法是新增 `actions.wait_for_feature_list(page, timeout, selector=...)`，恢复分支传
    `selectors.PS_USER_FEATURE`——判据是"**即将读取的那一类行**已经存在"，而不是"页面上有点
    东西"。它的 `minimum` 只数数量、不做名字匹配，所以全仓唯一的行匹配规则
    （`match_user_feature_row_indices`）没有被复制成第二套。
  - **不要**顺手把共享的 `wait_for_panel_rows` 改严：切标签的就绪判据依赖它更宽的条件，
    需要的严判据只属于"刚重载过、马上要枚举行"的调用方。
  - 判决分级不变：等满仍读不到时，恢复后依然是 `null` + `retryVerify`，绝不是 `false`
    ——"页面没渲染"和"编辑没生效"必须是两种答案。
  - 测试怎么建模这个竞态：假页用 `reload_render_polls`（>0 = 重载后要花几次等待才出现行，
    负值 = 永不出现），并且**让宽判据在未渲染时也返回 True**。否则假页会比真机宽松，
    测试会掩盖这个竞态——这正是"测试替身不得比真实客户端宽松"那条规则的一个实例。
- 工具栏：`.toolbar-item`，按钮 `.tool.is-activatable.is-button`；文字标签
  `.tool-label.hide-in-toolbar` 是**隐藏的**，`browser_click(text=...)` 点不到，
  要按 `.toolbar-item` 的 textContent 找到后点内部按钮。
- 「添加自定义特征」对话框 `.feature-studio-insert-dialog`：
  - 标签 `.os-dialog-tab`：`当前文档` / `其他文档`；
  - 文档名 `.select-item-dialog-document-name`；
  - 若提示「没有可用的特征。… 创建一个版本」，说明 Feature Studio 未发布版本，
    需先在文档里创建版本后自定义特征才可插入。
- **已插入特征的参数对话框 `.feature-dialog`**（2026-09-20 实测，0 REST 配额）：
  双击特征行打开，接受按钮 `.ns-dialog-button-ok.button-ok`。参数化生成的特征
  （precondition 里有 `annotation { "Name" } isLength(definition.…)`）在这里显示
  每个维度的可编辑数值框，实测读出 `baseRadius 10 mm / pitch 6 mm / ridgeWidth 2 mm
  / ridgeHeight 2 mm / length 30 mm`；改成 `12 mm` / `40 mm` 后 ✓ 生效并持久化。
  precondition 为空的特征在这里**没有任何可编辑字段**，只显示内部几何图元
  （extrude / helix / sweep / boolean），这是"生成的特征不像官方特征"的根因。
  - 面板根是 `.ns-dialog-panel.feature-dialog`，右上角是绿色 ✓ 与红色 ✗；**行名带着
    自定义特征徽标**：`read_partstudio_features` 读到的行名是 `Sr Spiral ridge 1`，
    而对话框标题是**裸名字** `Spiral ridge 1`（`Sr` 是渲染出来的徽标文本，不是名字的
    一部分）。按名字定位特征行时要用**带徽标的那份**，因为读与定位都取自同一个
    `innerText`。
  - **"参数对话框是否开着"可以不靠人、也不靠 L1 原语判断**（2026-09-20 实测，受控对照：
    同一元素同一特征，只让面板开关不同）：开着时用户特征行 `className` 为
    `os-list-item related-highlight edited selected ns-user-feature`、零件为
    `os-list-item edited`；关闭时回到 `os-list-item ns-user-feature`、零件 `os-list-item`
    ——与编辑前的基线逐字相同。`read_partstudio_features` 本来就返回这个字段，所以
    `browser_get_partstudio_features` 足以回答这个问题。注意 `edited` 并不表示"文档有
    未保存改动"：真改落库后关闭面板，该 class 就消失了。
  - 这个后端（WSL 侧 `onshape` 连接）是**固定工具视图**：`browser_eval` 返回
    `unknown tool`，`mcp_tool_view(action="set")` 返回 `shared_view_fixed`，
    所以"页内求值/截图/按键"这类 L1 原语在这里都不可用；需要它们才能回答的问题
    必须转成"人看屏幕"或"用已有的读类工具找等价判别条件"（上一条就是后者的例子）。
- **行的身份与下标的必须来自同一次枚举，绝不能拿"读过筛的读"去比"照数数的定位器"
  （2026-09-20 实测，已修复）**。同一个面板上，`read_partstudio_features` 把
  `Sr Spiral ridge 7` 读成唯一命中，而
  `page.locator('.os-list-item.ns-user-feature').filter(has_text='Sr Spiral ridge 7')`
  连续四次（含两次页面重载）给出非 1 的计数；改成"读计数 vs 定位器计数"之后更糟：
  `read_partstudio_features` 的采集 JS 末尾有 `.filter(f => f.name)`，会丢掉
  `innerText` 与 `textContent` 都为空的那个 `.os-list-item`，而定位器照数。两个规模
  完全不同的 Part Studio 上恒差 +1（`Spiral ridge PS` 读 11 / 数 12；`Part Studio 1`
  读 1 / 数 2），于是"计数必须相等"的守卫在**每个**元素上都拒绝，
  `browser_edit_feature_parameters` 真机整体不可用。（修复后在 `Spiral ridge PS`
  复测：`featureRows` 12 项、`locatorRows` 12、面板就绪 16 ms，且该无文本节点排在
  **最后**——所以当时的名字序号并没有偏移，拒绝完全来自那次计数比较。）
  **集合差不是页面变化**，所以"筛过的读"与"照数的定位器"永远不能互为前置条件。
  修法不是放宽守卫，而是让两者成为同一个集合：`_USER_FEATURE_ROWS_JS` 在页面内一次
  `querySelectorAll` 同时返回 `count` 与 `names`（含无文本行、按 DOM 顺序），
  名字匹配与 `rows.nth(index)` 的下标都取自这一份列表；定位器计数只留作**过期检查**
  （两次查询之间页面真变了才拒绝）。`browser_edit_feature_parameters` 先
  `wait_for_panel_rows` 等面板渲染，拒绝时一并报出
  `featureRows` / `matchedRows` / `locatorRows`。旧文案 "must match exactly one row"
  既没说 0 也没说多个，这正是它无法从外部诊断的原因。
- **无文本行确实存在，但它的位置不是契约（同批 + 修复后复测）**：页面上有一个无文本的
  `.os-list-item.ns-user-feature` 节点，与具体元素无关，会被"按名字读"丢掉、被定位器
  数上。**修复后在 `Spiral ridge PS` 复测：它在 12 个节点里排在最后一个**——所以旧代码
  真正触发拒绝的是"计数必须相等"（12 ≠ 11），不是下标偏移；名字序号当时其实是对的。
  结论按这个更准确的版本记：**不要依赖它在哪一端**，它只是 Onshape 的内部节点。同理，
  `count_custom_features` 这类预算口径必须明确是"数有名字的行"还是"数 DOM 节点"，
  否则预热预算会虚高。
- **工具事务可能比传输上限活得久：拆两段，别让"确认"拖住"提交"（2026-09-20 实测）**。
  `browser_edit_feature_parameters` 一次做完"提交 + 确认"时，在 11 个用户特征的 Part Studio 上
  耗时 **61.7 s**（桥的 correlation 记录：请求 236 B → 响应 2499 B，间隔 61.7 s），而客户端/
  中继在 60 s 先超时，返回 `MCP error -32001: downstream_timeout`。旧定位拒绝是 <1 s、
  约 618 B 的载荷，所以"61.7 s 后产出了多千字节响应"本身就证明它已经越过定位并走完对话框
  流程；但 `parametersApplied` 与写入结果**无法从客户端证实**。**"61.7 s = 模型重算花了
  61.7 s"这个归因已被第四轮实测推翻**：61.7 s 只比 `PS_DIALOG_CLOSE_TIMEOUT_MS = 60_000`
  多一个开销，而实测的关闭延迟要么 ≤5 ms（空操作 accept）、要么 >95 s（真改参数）。
  随"是否真改参数"跳变的量不是"重算时长"，那 60 s 是旧代码**自己的有界等待被跑满**。
  **修法：把"提交"与"确认"拆成两段**——点击 accept 就是提交，对话框关闭只是"重算完成"的
  信号。默认段在点击 accept 后立刻返回 `applyState: "pending_verification"`、
  `parametersApplied: null`（**绝不返回 `False`**：写入并未失败），并带 `verifyWith` 指向
  `browser_verify_feature_parameters`；第二段用更小的预算（25 s）等对话框关闭，关不上就返回
  `parametersApplied: null` + `retryVerify: true`，**不猜**——对话框还开着时行列表可能仍是
  accept 之前的 DOM，用它宣称"已重新生成"就是编造。要一次做完的调用方显式传
  `wait_for_regeneration=true`。同一现象还伴随页面掉到 `about:blank` 与会话登出（因果未
  确立，只按观测记录），所以长事务不要为了拿返回值而重跑。**凡可能超过传输上限的浏览器事务，
  超时都不等于失败，重试可能重复执行。**
  - **两段式已真机认证（2026-09-20 第四轮，0 REST 配额）**：第一段在 accept 后立刻返回
    （`applyState: "pending_verification"`、`parametersApplied: null`、`readbackOk: true`、
    带 `verifyWith`），面板关闭后第二段给出完整判决 —— `verified: true`、
    `parametersApplied: true`、`regenerationOk: true`、`persistenceOk: true`、
    `persisted.baseRadius` 与请求值逐字相符（同一元素上两次，`elapsedMs` 5 与 4）。
    **安全属性也立住了**：三次真改参数的第一段都返回 `pending_verification`，
    第二段返回 `parametersApplied: null` + `retryVerify: true` 而**没有**编造
    `applied: false`，也没有再把载荷丢给 60 s 传输上限。
  - **仍未闭合的一点**：真改参数时面板长时间不消失，所以"等面板关闭"这条判据
    在传输安全预算内**无法**给出判决（`retryVerify: true` 会一直重复）。
    能用的判决路径是本轮实测过的：**重载页面**（丢掉还开着的面板，不撤销已提交的改动）
    → 重新打开对话框 → 读 `before` 与请求值比对。另注意两个字段是**初值而非测量值**，
    不要当数据读：第一段的 `accept.waitMs` 恒为 `0`（该路径根本没做那次等待，不是
    "等了 0 ms"），第二段未关闭时的 `featureState: []` 是空初值，不是"没找到行"。
- **必须有工具能把"已有标签"设为活动，否则读类工具没有目标可指（2026-09-20 实测）**。
  `browser_get_partstudio_features`、`browser_edit_feature_parameters` 这类工具都作用于
  **当前活动标签**，而此前只有 `browser_create_tab`（新建即激活）与
  `insert_custom_feature(part_studio_tab=…)` 内部那段标签点击会切标签；
  `browser_rename_tab` 双击标签名进入改名模式**并不会**让该标签变成活动（实测 `active`
  仍是原标签）。后果很具体：想在一个小元素上做端到端验证都做不到，只能撞 11 特征的大元素，
  于是又踩上 60 s 上限。现在由 `browser_activate_tab` 补上：按 `data-id`（标签列表本身
  就给 id）或"恰好一个同名标签"选择，**绝不按位置**（标签条是 `ng-repeat`，增删标签会
  重编号），判据是回读该 `data-id` 自己的 `active` 类；`content="partstudio"` 时再等特征树
  标题与行——切换过去的 Part Studio 分阶段渲染，立刻读会读到 0 行。
  **已真机认证（2026-09-20 第四轮）**：从 `Spiral ridge PS` 切到 `Part Studio 1`，
  `activated: true` / `clicked: true` / `activeBefore` 与 `activeAfter` 是**两个不同 id**，
  `wait.elapsedMs` **357 ms**，`contentReady.headerVisible: true`、行等待 6 ms；
  标签已经活动时不点（`alreadyActive: true, clicked: false`）但仍做就绪等待（60/68 ms），
  所以它同时是"切换"和"就绪门"。
- **`arg` 是 keyword-only；写错会被 `except Exception: pass` 吞掉（同批发现）**。
  playwright-python 的 `wait_for_function(expression, *, arg=None, timeout=None, …)`
  里 `arg` 只能按关键字传。`transactions.py` 有两处（切监控目标、复制标签页）按位置
  传入字典/列表，实际抛 `TypeError`，而两处都包在 `except Exception: pass` 里，
  于是**等待从未发生且没有任何迹象**。现在调用点、测试双代和静态守卫三者都强制
  关键字形式。同一处还发现 `arg=list(set)`：集合迭代顺序随进程的字符串哈希种子
  变化，每次发送的参数列表不同、结果不可复现，已改为有序列表。

## 5. 选择器优先级（写自动化时）

1. 唯一 `id`：`#search-box`、`#user-notification-status`、`#create-new-type`。
2. 语义 class + 文本：`tab-list-item.os-tab-bar-tab`（按 `.os-tab-name` 文本定位）、
   `.tool.is-activatable.is-button`（按 innerText 定位「提交」「Module outline」等）。
3. `aria-label`：导航按钮都有明确 aria（「在新窗口中将您导航到…」）。
4. 避免：脆弱的 `ng-star-inserted` 等框架类；AG Grid 行号/列号。

## 5.5 部署 FeatureScript（0 配额，已验证）

`browser_deploy_featurescript` 全流程已实测跑通：

1. `open_login_page()` 恢复登录后进入 FS 编辑器页；
2. `actions.write_featurescript_editor()` 用 Ace API `ed.setValue()` 写入全文；
3. 写入后「提交」按钮从 disabled → enabled（`actions.commit_button_state()` 可读状态）；
4. `actions.click_commit()` 点击提交，3 秒后按钮回到 disabled = 提交成功；
5. 提交后读回编辑器并比对，返回 `verified: true` 仅当页面源码与提交内容完全一致；
6. `browser_fs_read_notices` 与 Ace annotations 共同构成编译证据；任一 blocking
   warning/error 或通知面板不可读都会使 `compiled:false`；
7. 每次已提交尝试把完整源码、`compile-result.json` 和 manifest 原子写入
   `onshape_browser_mode/outputs/fs_diagnostics/<capture-id>/`，结果返回
   `diagnosticCapture`；实验性 `browser_fs_capture_diagnostic` 可随时补采当前状态；
8. 实测：dry_run 纯本地预览（不启动浏览器）→ 部署修改（23907 字符，`verified:true`）→
   恢复原内容（23875 字符，`verified:true`）。

关键 JS（`actions.py`）：
- 读全文：`ed.getValue()`
- 写全文：`ed.setValue(text); ed.clearSelection(); ed.moveCursorTo(0,0)`
- 提交按钮：`.tool.is-activatable.os-primary.is-button`，文案「提交」，
  `className.includes('disabled')` 表示无未提交改动。

## 5.6 FeatureScript 诊断回路（通知采集 → 归一化 → 回落本地）

**观察层保持不变**：`actions.read_featurescript_notices()` 原样返回页面上读到的
通知行；`actions.read_featurescript_compile_status()` 才做派生。

- **全部消息**：一个 `.feature-script-notice-table` 可能含多个
  `.notice-location-message` 段落。采集器（`actions.FS_NOTICE_SNAPSHOT_JS`，模块常量）
  现在返回 `messages` 数组，`text` 仍是第一段，老调用方不受影响。
- **跨元素与过期容器（实测修正，2026-09-20）**：派生层只把**活动标签的新鲜通知**算进
  `errors` / `compiled`（部署门不受影响），但采集器**不再跳过其他文档元素**、也**不再
  跳过 `.notices-out-of-date` 容器**——Part Studio 的重生成错误恰恰带着
  `notices-out-of-date` 标记、躺在**非活动**元素的普通 `.feature-script-notice-table`
  里。每条通知因此带 `tabName` / `isActiveTab` / `outOfDate`；
  `read_featurescript_compile_status()` 另给 `activeTabName`、`elementNotice*`、
  `staleNotice*`、`documentClean`、`noticeContainerTitles`，以及静默容器存在时的
  `noticePaneStructure`（有界：容器摘要 + 关键词过滤后的 pane class 名）。
- **severity 优先级**：通知表自身 className 加全部后代 className 里出现 `error` 即判
  `error`，否则 `warn`→warning、`info`→info，都没有再退回 warning。历史上只看标题图标，
  把 Part Studio 的 error 记成 `info`——这是检索盲区的另一半，两处一起改才捞得回来。
- **归一化编码**：每个派生诊断带 `code` / `codeBasis` / `codeStable`，便于归类而不用
  解析自由散文。四种 basis：
  - `errorstringenum`：文本里出现 vendored `ErrorStringEnum` 定义过的全大写 token；
  - `errorstringenumDescription`：整条消息恰好等于**唯一**一个 code 的英文描述；
  - `compilerMessage`：我们自己归纳的编译器消息族（前缀 `FS_`），标注为不稳定；
  - `unclassified`：没匹配上，原样保留并计数，不硬塞。
- **源码行**：落盘产物里每条诊断附 `sourceContext`（行号、源码行、caret、截断标记），
  诊断因此自包含、可离线复现。
- **去重 + 频次**：同一条缺陷同时出现在 Ace annotations 和通知面板时合成一个 group，
  记录 `sources` 与全部 `locations`，所以 `count` 是缺陷数而不是通道数。
- **回流产物**：`save_featurescript_diagnostic()` 除原有 `featurescript.fs` /
  `compile-result.json` / `manifest.json` 外写入 `diagnostics.json`，并在返回值里给出
  有界的 `corpusEntry`（`{source 摘要, 归一化诊断, 服务端结论}`），供本地分析器在没有
  MCP 宿主机文件系统访问权时也能消费。`load_retained_diagnostics()` 反向读取历史采集，
  旧格式采集标记为 `normalized: false` 而不是丢弃。
- **编码表来源与规模**：`ErrorStringEnum` 被上游标为 `@internal`，**不在生成的 FsDoc
  索引里**，唯一本地来源是 `onshape_docs/reference/raw/std-library/errorstringenum.gen.fs`。
  实测：1759 个 code、1703 条描述、其中 **20 条描述被多个 code 共用**（如
  "Error regenerating."、"Failed to create assembly instance."）——这些一律不猜，落到
  `unclassified`；35 个 code 无描述只能靠 token 匹配。可用 `ONSHAPE_FS_ERROR_ENUM`
  覆盖路径；读不到时 `codeTable.available: false` 并退化为消息族匹配，不静默失败。
- **告警级**：编码与摘要只用于归类/告警，**不阻断上传**；vendored 索引可能滞后线上。

已验证边界（诚实记录）：
- 归一化、源码行、去重汇总、采集产物、历史读取由 `dev/tests/test_fs_diagnostics.py`
  覆盖（离线、确定性）。
- 采集器字符串本身由 `dev/tests/test_fs_notice_collector.py` 在 **node + stub DOM** 下
  执行**同一份生产字符串**（25 个用例），覆盖多消息、severity 回退与优先级、行/列非数字、
  跨元素通知保留、`notices-out-of-date` 容器读取并打标、无标题容器按活动标签处理、
  静默元素、空表跳过、不可见 toggle，以及「读不到 pane 时绝不报 `documentClean`」。
- **已实机（2026-09-20，浏览器腿，0 REST）**：在 Feature Studio 标签下
  `browser_get_fs_compile_status()` 读到了 `tabName: "Part Studio 1"`、
  `isActiveTab: false`、`outOfDate: true` 的 error，文本与调用栈完整
  （`Feature Studio 1 (gfCellCount)` → `(const gfSocketPockets)` →
  `onshape/std/feature.fs (defineFeature)` → `Part Studio 1 (GF Socket Pockets 1)`，
  line 100/107 column 9），`elementErrorCount: 1`、`documentClean: false`，而同一时刻
  `compiled: true`。修好模型后重读，Part Studio 容器只剩 `Result: Regeneration complete`，
  `documentClean: true`、`elementErrorCount: 0`、`staleErrorCount: 0`。
  证据：`onshape_docs/verification/notice-retrieval-2026-09-20.md`。
- **仍未验证**：一个通知表含**多个** `.notice-location-message` 段落的 `messages` 假设
  仍只有 stub DOM 证据；实机记录里每张表都只有一段。另有更早的实机记录
  `dev/button-map/scan-fs-notices.json`（28 条通知、4 条样本文本）。

## 6. 已知坑

- 多标签漂移：人工登录可能在新标签打开 documents，旧 signin 标签仍残留。`status()`/`start()`
  会遍历 `context.pages` 优先选已登录应用页，并关闭其余标签。
- Playwright sync API 绑定创建线程；桥接必须**主线程串行**处理客户端，否则报
  `Target page, context or browser has been closed`。
- 同一 profile 已由其他进程持有时，新的 `launch_persistent_context` 也可能以同一错误
  退出。当前进程只能通过 `browser_session(action="release")` 释放自己的 owner；
  不能删除锁文件或强杀另一 owner，跨进程冲突转交 Operator 处理。
- `launch_persistent_context` 命令行末尾固定带 `about:blank`，这是正常启动页；
  是否恢复上次标签取决于上次是否强杀（崩溃恢复）。
- 中文 Windows 下 Python stdout 默认 GBK；MCP 协议读写必须走 UTF-8 字节流。
- **`edge://downloads-hub/` 曾卡死所有页面级调用（实测并修复 2026-09-20）**：STEP 导出
  之后 Edge 会多出一个下载中心 target。曾经的症状是 `browser_get_page_tabs`、参数读写等
  页面级调用一律以 `MCP error -32001: downstream_timeout`（约 32 s）结束，而
  `browser_session(status)`、`onshape_api_quota`、`bridge_control` 仍可用。
  根因链（不是"标签页太多"）：页级事务先跑 `_enforce_single_working_page` →
  `SyncSession.reconcile_pages(context.pages)` → 共享库对**交给它的每一个页面**调用
  `page.close()` → 而对 `edge://downloads-hub/` 调 `page.close()` **永不返回**，这个
  target 于是永久占住页面通道。
  已落地的修法（`onshape_browser_mode/session.py`）：浏览器内部页面
  （`edge://`、`chrome://`、`devtools://` 等）**绝不进入** `reconcile_pages` 的清单，也
  **绝不用 Playwright 关闭**；关闭改走常驻浏览器自己的回环 DevTools
  （`/json/list` 匹配 url → `/json/close/<targetId>`），受 2 s socket 超时限制。
  `browser_export_step` 在 `save_as` 之后同样只会请求关闭此类页面，因此导出自身不再制造
  这个坑。
  **两个必须分清的事实**：`/json/close/<id>` 被接受 ≠ 目标消失。实测 Edge 会对
  `edge://downloads-hub/` 接受关闭请求，而该 target 仍以 "Target is closing" 留在
  `/json/list` 里（CDP 关不掉、激活后再关也关不掉），**且这不影响可用性**：修复后
  `browser_get_page_tabs` 在该 target 仍在列表中的情况下照常秒回。所以
  `browser_export_step` 分开报告 `browserInternalPagesCloseRequested`（被接受的关闭请求数）
  与 `browserInternalPagesRemaining`（仍然在列的内部页面数，未探测/不可达时为 `null`），
  不把"请求被接受"说成"页面已关闭"。
  回环 DevTools 端口只在 `browser.resident = true` 时才使用：
  `resident_port` 有默认值，无此门禁时非常驻部署会向恰好监听该端口的**无关进程**发关闭请求。
  曾经的临时绕过手段（手工 `curl /json/close/<id>`）已不再需要，也**不要**为此重启节点。
- **页面通道卡住时透明重启会被拒**：卡住的页面请求在服务端仍算 active，重启返回
  `control_failed: active_requests: transparent restart requires an idle shared backend`。
  先清掉卡住页面的来源（上一条），而不是反复重试重启。
- **浏览器动作 8 次/分钟上限**：项目运行器撞到上限直接抛
  `ActionRateExceeded: browser action cap reached (8 actions/min); retry in about 17.8s`，
  它不会自己等；直接调用 browser_* 工具则内部排队。多步项目在第 4 步被打断时，优先改用
  单次直接工具调用补那一步，而不是重跑整个项目。

## 7. 标签（Feature Studio / Part Studio）管理

- 标签元素：`<tab-list-item class="os-tab-bar-tab" data-id="<elementId>">`，
  名称在 `.os-tab-name`；`data-id` 即 elementId。
- 实测残留的 `#context-menu-layer` 即使没有菜单项也可能覆盖标签并拦截真实点击；
  高层标签事务应先检查其 `pointer-events` 与可见尺寸，仅在确实阻塞时发送一次
  `Escape`，再执行标签点击。不要在任意普通点击前无条件发送 `Escape`，否则会关闭
  调用方正在操作的对话框。
- 右键上下文菜单：`ul.context-menu-list.context-menu-root` 下
  `li.context-menu-item`，文本为 `删除` / `重命名` / `属性…` / `在新浏览器页签中打开`。
- **必须用 Playwright 真实点击**（`locator.click()` / `click(button="right")` /
  `fill` / `press`）：`el.click()` 这类合成事件会被 Onshape 忽略——右键菜单项、
  删除/重命名都不会生效（与特征树删除同因）。
- 重命名：`tab.click(button="right")` → `li.context-menu-item` 含「重命名」→
  `input.fill(new_name)` → `input.press("Enter")`。
- 删除：右键 → `li.context-menu-item` 含「删除」→ 通常无二次确认对话框，删除后
  该标签消失；被删标签会先激活再消失，其余标签顺序保持。
- 删除/重命名都是 0 REST 配额的 UI 写操作，仍需 `confirm_mutation=true`。
- **"已删除"绝不能用**位置**上的节点 detach 判定（2026-09-20 实测，已修）**。
  `browser_delete_element` 原来等的是 `locator.nth(i).wait_for(state="detached")`，但
  SPA 只给节点加上 `hidden` 类（`ng-class` 由 `tab.getIsRemoved()` 决定），节点仍在
  DOM 中，于是 30 秒后超时报 `deleted: false`——而 `browser_get_page_tabs` 已经不再
  列出该标签，删除其实**成功**了。第二个陷阱就在同一个 `nth`：标签条是 `ng-repeat`
  列表，删掉一个标签会把它后面的节点**重新编号**，`nth(i)` 于是在下一次解析时落到
  刚补位的那个标签上——它当然还 attached，所以这个等待**永远不可能**被满足。正确判据
  是按 `data-id` 等（`wait_for_tab_removed`：该 id 的节点数为 0，或每个该 id 的节点都带
  `hidden`）。修复后实测：删除一个新键的 `Feature Studio 1` 返回 `deleted: true`、
  `removal.waited: true`、**274 ms**（旧代码是 30 s 超时）。同时要记住原始标签读取
  **不能**参与判据：`list_document_tabs` 的采集 JS 做的是 `querySelectorAll('.os-tab-bar-tab')`
  全量映射、**完全不过滤 `hidden`**，所以刚刚删完那一瞬它仍会把该节点列出来
  （同一返回里的 `stillListedIds` 就等于被删 id），几百毫秒后节点真正 detach 才不再列出
  ——"还列着"是时序相关的现象。因此把原始读取只当诊断信息返回，绝不用它推翻判据。
- `dev/button-map/scan-app-shell.json` 证明 Part Studio 标签和 part row 的右键菜单都出现
  `导出…`。登录恢复后又实测了 Part Studio export dialog：根节点
  `.modal.export-dialog`；文件名 `#export-filename-input`；格式
  `#export-format-dropdown`；STEP 版本 `#step-export-version-dropdown`；自定义单位
  checkbox `#custom-step-units-checkbox`；单位 selector
  `[ng-model='options.stepExportUnit']`；下载方式 `#export-options-dropdown`；单独文件
  `[ng-model='download.shouldExportPartsAsIndividualFiles']`；隐藏实例
  `#export-hidden-entities-checkbox`。可稳定选择 STEP/AP242/Millimeter/下载，并取消对话框。
- `browser_export_step` 使用上述 live-observed selector，先激活并核对 URL 中的
  document/workspace/element IDs，再要求单一非 ZIP `.step`/`.stp` download，保存到
  browser-owned staging 并写 SHA/provenance manifest。一次显式授权的真实提交已验证
  AP242/Millimeter/直接下载，得到 34,084-byte STEP 且独立 SHA 复算一致。
- Windows browser owning mode 启动 `wsl.exe`/converter CLI 时不得显示 console；
  `CommandStepConverter` 在 Windows 固定传 `CREATE_NO_WINDOW`。首次 CadQ field run 暴露
  了可见 CMD 窗口并形成此要求，后续 CLI backend 必须保留 windowless 断言。
- Geometry dependency 复用顺序固定为 explicit config → repo 上级目录的 sibling
  venv → global Python PATH → Windows/WSL 对端的 sibling/global 环境。扫描有目录、
  distro 和 timeout 上限；公开结果只含 opaque `candidateId`、来源和版本，不含 executable/
  argv。configure 工具必须重新扫描 candidate，不能接受调用方路径。若没有 candidate，
  status 返回 `ask_before_install` + `requiresUserConfirmation=true`；agent 必须询问用户，
  不得自动安装。

## 8. 标签页创建菜单的真实位置

- `.document-tabs-button` 是**测量/分析/质量属性**按钮组，不是“+ 新建页签”按钮；
  不要用它定位创建菜单。
- 创建页签的下拉项常驻 DOM（`a.dropdown-item`，隐藏状态），用 JS 直接
  `el.click()` 即可创建，不必先真实打开菜单。文本：`创建 Feature Studio`、
  `创建 Part Studio`、`创建装配体`、`创建工程图…`、`创建 Variable Studio` 等。
- 因此 `browser_create_tab` 采用“JS 点隐藏项”，与右键菜单必须真实点击不同。
- 工具只有在标签列表出现新项时才返回 `created:true`。工程图可能先打开来源/模板
  对话框，此时返回 `triggered:true, created:false`，不能把打开对话框当作创建成功。

## 9. 工程图编辑器在跨域 iframe 内

- 工程图标签加载后，实际编辑器位于 `iframe[src^="https://production-drawing-"]`，
  **跨域**（与 cad.onshape.com 不同源）。`browser_eval`/`browser_click` 只作用于
  主框架 `page.locator`，受同源策略限制无法进入该 iframe；尺寸标注工具也只在
  iframe 内。
- 后续要操作工程图，需要 frame-aware 工具（Playwright `page.frames` 按 URL 匹配
  目标 frame，再在其内部 locator），或在 bridge 内以 CDP 访问。
- 工程图加载慢：`正在加载工程图…` 长时间不消失时可 `browser_session(action="reload")`
  （或 `location.reload()`）刷新；若源 Part Studio 已被删除，工程图会一直卡在加载。


## 10. Frame-aware 通用操作

- `browser_inspect` / `browser_eval` / `browser_scroll` / `browser_click` 接受
  `frame_url` 子串。每次调用都重新遍历 `page.frames`；无匹配或多匹配会返回明确错误，
  不缓存可能 detach 的 Frame。
- `DrawingPage` 默认匹配 `production-drawing-`，Playwright 通过 CDP 可以驱动跨域
  frame；浏览器同源策略只限制主页面 JavaScript 直接访问 iframe DOM。
- `browser_wait` 支持 element/text/url/network_idle/frame 条件且硬上限 60 秒。SPA 的
  network-idle 可能超时，此时返回结构化失败，不无限等待。

## 11. 可信键盘与人工录制

- `browser_press_key` / `browser_type` 使用 locator 的真实 Playwright 输入事件；
  `browser_type` 以 `target_text` 表示目标可见文本，`text` 专用于输入内容。
- `browser_watch` 页面绑定捕获 click/input/change/keydown，并继续记录 URL、response
  status/content-type 和 dialog。录制不包含 request/response body、header 或 cookie。
- `save` 写到忽略的 `dev/watch-sessions/`；`verify` 对提交的顺序模板逐项匹配，避免
  把一次偶然 URL 命中当作完整工作流证据。输入框 value、单字符 key 与 URL query/fragment
  会在进入录制前丢弃，保存路径也限制在配置的 watch 目录。

## 12. 状态缓存与结果边界

- `browser_get_page_tabs` 返回每个 tab 的 `data-id`。`browser_sync_rest_state` 仅在显式
  调用时把 did/wid/eid 和 tab 表合并进 REST 模式拥有的状态文件，保留配额与手工键。
  `dry_run` 不启动浏览器也不写文件；真实本地写入要求 `confirm_mutation=true`。
- 装配工具要求显式 `instance_selector`，选择和验证不得退回整页文本。2026-08-21 的
  只读 DOM 扫描确认实例行 selector 为
  `.ns-tree-root .ns-assembly-instance-row.is-instance`；插入 dialog 行也经只读扫描确认。`source_names` 表示 dialog 中的 Part Studio 标签，`instance_names` 表示插入后树中的预期零件实例名，两者按索引对应，证据在
  `dev/button-map/scan-assembly-instances.json`；固定/分组在当前
  DOM 只能确认动作已触发，返回 `verification: action-triggered`。尺寸工具支持 DOM
  selector count 增量，或 Drawing canvas 的按键 + 相对坐标操作并比较前后 screenshot
  SHA-256；只有对应读回条件满足时，高层工具才返回 `assembled:true` / `drawn:true`。
- 2026-08-25 的 app-shell / Drawing 只读扫描记录在
  `dev/button-map/scan-app-shell.json`。Drawing 的实际四视图位于 canvas 内，DOM
  view selector 返回 0；`browser_draw_part_with_views` 的视图阶段因此还要求恰好一个新 tab，
  并解码 main-canvas PNG，排除图框/标题栏后检查主体墨迹比例和空间集中度。
  实测 1240×694 fixture 中有四个投影视图，证据图为
  `dev/button-map/scan-drawing-four-views.png`。不可见的 preview/drawer 候选仍标记
  unverified，读取工具返回结构化 absence/unknown。
