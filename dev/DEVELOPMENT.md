# 开发经验与计划（MCP 工具架构 / browser 自动化线）

> 本文档记录 MCP 工具架构、动态暴露和 Browser mode 的开发决策与计划。
> 可复用的页面结构、选择器和工具经验见
> `onshape_docs/experience/browser-automation.md`；零配额建模流程见
> `onshape_docs/experience/browser-modeling.md`.

## 1. 架构决策（已落地）

- 四包结构：`mcp_main`（MCP 协议/工具注册）、`onshape_docs`（离线文档）、
  `onshape_rest_api_mode`（REST API，配额保护）、`onshape_browser_mode`（浏览器自动化）。
- 浏览器只在 Windows 跑；Linux 只保留 stdlib 中继，不装 Playwright。
- `bridge_server.py` 从“每连接拉子进程”改为**常驻进程内 dispatch**：Onshape
  关浏览器即登出，浏览器必须存活于跨客户端重连的常驻进程里。
- 单工作页规则统一收口在 `BrowserSession._enforce_single_working_page()`。

## 2. 经验归档边界

GBK 编码、Playwright 线程绑定、SPA 登录判定、强杀恢复和多标签漂移等
可复用结论已统一归档到 `onshape_docs/experience/browser-automation.md`。
本文不保留第二份行为说明，避免开发计划与当前经验互相矛盾。

## 3. 已完成（git 链）

基础设施：

- UTF-8 协议修复；Windows 重启自愈（计划任务 `OnshapeMCPBridge`）。
- 本地 HTTP 代理支持（`browser.proxy_server`，当前 `http://127.0.0.1:10808`）。
- 常驻进程内 bridge + 浏览器登录态跨客户端保持；启动清理残留标签 +
  优先保留已登录页 + `lastAppUrl` 入口恢复。
- 自愈脚本：`mcp_main/bridge/windows/restart-bridge.bat` / `.ps1`——强杀自动化
  Edge + 旧 bridge 后重启，强杀保留登录态。

浏览器工具（均已实测）：

- 只读探索：`browser_session` / `browser_watch` / `browser_inspect` /
  `browser_scroll` / `browser_click` / `browser_eval` / `browser_reload`。
- `browser_deploy_featurescript`：写 Ace 全文 → 提交编译 → 按钮 disabled 确认 →
  读回校验 `verified:true`（0 REST 配额）。
- `browser_open_document` / `browser_read_featurescript`：解析 did/wid/eid；
  读回 Ace 全文 + 页面 id。
- 上传+编译+建模闭环：`browser_get_partstudio_features` 读特征树与 `零件数 (N)`
  （Branch Cable Trophy 132 零件实例化验证）。
- 标签管理：`browser_create_tab`（Feature Studio / Part Studio / Assembly；Drawing 启动来源/模板流程）、
  `browser_rename_tab`、`browser_delete_tab`；`browser_click` 增加
  `button`（left/right/middle）、`double`、`modifiers`（Ctrl 多选）。
- `browser_insert_custom_feature`（工作区下拉按条目点击）+ `browser_create_document_version`。
- 模块接口验证文档实战：12+ 个 Part Studio 收敛为 2 FS + 2 PS + 1 Assembly + 2 Drawing；
  Part A/B 均 `零件数 (1)`。

## 4. 开发计划完成状态

- [x] **page objects**：`onshape_browser_mode/pages/` 已提供
  `DocumentsPage`、`FeatureStudioPage`、`PartStudioPage`、`AssemblyPage`、
  `DrawingPage`；frame 与 locator 解析统一在 `BasePage`。
- [x] **与 REST 模式打通**：`browser_sync_rest_state` 显式把浏览器观察到的
  document/workspace/element id 合并到 REST 模式拥有的 `onshape-state.json`；`dry_run`
  不写文件，真实同步要求确认。它不隐式查询、不覆盖配额和手工维护字段。
- [x] **人工录制验证管线**：`browser_watch` 已捕获 click/input/change/keydown、URL、
  network 与 dialog，可 `save` 到忽略目录，并用提交的
  `dev/fixtures-capture/watch/fs-edit-submit.template.json` 做顺序验证。实际录制由登录态
  操作者执行，录制器不保存 header/body/cookie。

## 4.1 四大语义分层（已落地）

选择器只存在于通用操作/page object/`selectors.py`；高层工具只组合低层语义。

### 1) 通用操作（原子，零按钮语义）

- ✅ `browser_click`（left/right/middle、double、modifiers）/ `browser_scroll` /
  `browser_inspect` / `browser_eval` 均支持可选 `frame_url`。Playwright 通过
  `page.frames` 驱动跨域 `production-drawing-*` frame。
- ✅ `browser_wait`：有界等待 visible/hidden/attached/detached/text/url/network_idle/frame，
  上限 60 秒，替代流程中的盲目固定等待。
- ✅ `browser_press_key` / `browser_type`：使用可信 Playwright `press` /
  `press_sequentially`，支持 frame、dry-run 和确认门。
- ✅ `browser_reload` / `browser_session` / `browser_watch`。

### 2) 低级语义（事务原子）

- ✅ 文档/标签：`browser_create_document`、`browser_open_document`、
  `browser_create_tab`、`browser_rename_tab`、`browser_delete_tab`、
  `browser_delete_element`、`browser_get_page_tabs`。标签读回包含 `data-id`。
- ✅ 装配：`browser_insert_assembly_instances`、`browser_fix_instances`、
  `browser_group_instances`。四个装配工具都要求调用方提供 `instance_selector`，所有选择和
  验证只在该实例行作用域内进行，禁止命中同名文档标签。真实只读 DOM 证据已固化到
  `dev/button-map/scan-assembly-instances.json`，默认 selector 为
  `.ns-tree-root .ns-assembly-instance-row.is-instance`；插入 dialog 行也经只读扫描确认。`source_names` 表示 dialog 中的 Part Studio 标签，`instance_names` 表示插入后树中的预期零件实例名，两者按索引对应；固定/分组明确返回
  `verification: action-triggered`，不伪造未观察到的结构状态。
- ✅ 工程图：`browser_create_drawing` 从指定 Part Studio/Assembly 选择来源与模板；
  `browser_add_drawing_dimension` 在指定 drawing frame 中支持两类动作：DOM selector 模式
  要求 `verification_selector` 数量增加；实际 Drawing canvas 模式用 `tool_key`、相对
  `geometry_points` / `placement_point` 驱动，并要求操作前后 canvas screenshot SHA-256
  变化。无法进入 frame 或没有观察到对应变化都返回失败。
- ✅ 状态：`browser_sync_rest_state` 显式同步浏览器 id 到 REST 本地缓存。

### 3) 高级语义（多个事务原子）

- ✅ `browser_deploy_and_apply_featurescript`：确保 FS/PS 标签，写入并提交源码，可选
  创建版本，应用特征，返回 `{parts, partNames}`。
- ✅ `browser_build_part`：新建/复用 Part Studio、应用特征并解析 `零件数 (N)`。
- ✅ `browser_assemble`：新建/复用 Assembly、插入实例、可选固定/分组。
- ✅ `browser_draw_part`：创建工程图、添加尺寸并返回 frame/view 状态；只在 frame
  可读且所有配置尺寸成功时返回 `drawn:true`。

### 4) 顶级语义（fixture 驱动项目）

- ✅ `browser_run_project(project="module-interface-verification")` 读取
  `dev/fixtures-capture/module-interface-verification.json`，串行执行建文档、部署/建模 A/B、
  装配和工程图。
- ✅ 每步成功后原子写入
  `onshape_browser_mode/user_data/project-runs/<project>.checkpoint.json`；checkpoint 绑定
  fixture 与引用源码 SHA-256，计划变化后拒绝 resume。失败返回步骤索引、已完成步骤和 resume 提示，
  `resume=true` 只重跑未完成步骤。
- ✅ fixture 脚本路径限制在 `dev/fixtures-capture/`，fixture/checkpoint 递归拒绝
  authorization/cookie/token/secret/password/api-key 形状的键。

### 分层依赖总则

```
顶级语义 ──> 高级语义 ──> 低级语义 ──> 通用操作 ──> selectors.py / page.frames
   (脚本)      (中型流程)     (事务原子)     (原子动作)
```

- 每层禁止调用上层，可以调用任意下层。
- 新选择器/frame/等待结论同步沉淀进 `selectors.py` 与经验文档。
- 所有新写操作先走 pure-local `dry_run`，真实执行要求 `confirm_mutation=true`。


### 验证边界

- 当前完成证据是离线协议、Mock/fixture、状态持久化与失败路径测试；未对用户云端文档执行
  自动变更。实际 UI selector 首次运行前仍应先用 `browser_inspect` / `browser_watch` 录制确认。
- 工具不会把“点击成功”等同于模型成功：Commit 必须读回 disabled 状态，build 必须读到
  目标 user feature 与正零件数，装配实例必须在指定作用域可见，尺寸必须观察到 DOM
  节点增量或 canvas 图像变化。

## 5. 工具发现、动态暴露与类人原生建模计划（待实施）

### 5.1 问题与目标

随着 Browser mode 增加“类人原生建模”能力，L2 事务工具可能按草图、拉伸、旋转、
扫描、放样、圆角、倒角、抽壳、阵列、布尔等特征快速增长。继续让 `tools/list` 一次返回
全部 schema，会同时放大两类上下文成本：

- 工具成本：客户端可能在每轮把全部 tool description / input schema 注入模型。
- 引导成本：若主 instructions 同时解释所有模块和工具，模型还会重复读取大段导航文本。

目标不是删除完整能力，而是做渐进式发现：

```text
主 MCP（固定小入口）
  -> 四模块入口
  -> 模块子目录
  -> 四级语义 / 查询索引
  -> 当前任务需要的少量工具
```

验收目标：初始 `tools/list` 保持常数规模；打开模块后也只暴露 bounded candidate set；
完整 handler 仍可供高层流程内部组合，但不会自动进入模型上下文。

### 5.2 三个正交分类轴

禁止再用一个层级同时表达“代码归属”“业务能力”和“操作粒度”。工具目录采用：

```text
(module, submodule, semantic_level?)
```

- `module`：运行时、代码和安全边界，始终必填。
- `submodule`：同一模块内的能力族；主模块存在子模块时必填。
- `semantic_level`：可选的 L1-L4 发现标签，不是注册、权限或调用门。

对于没有子模块的叶节点主模块，允许两种等价写法：省略 `submodule`，或将
`submodule` 写成与 `module` 同名。目录层统一归一化为
`effective_submodule = submodule or module`；只有模块注册表声明 `hasSubmodules=false`
时才允许省略。存在子模块的主模块不得用同名占位绕过具体子模块选择。

四级语义是一项帮助 AI 快速判断工具粒度的约定，不要求每个工具强制填写，也不要求
调用方每次指定。未填写 `semantic_level` 时，工具仍属于对应子模块并可正常发现和调用。

首期四模块固定为：

1. `documentation`：项目知识、经验、验证记录和索引导航。
2. `featurescript`：FeatureScript 参考、版本、源码与语言能力。
3. `rest_api`：REST 参考、本地状态、配额、远程读取与写入。
4. `browser`：持久化浏览器、文档 UI、FS/PS、Assembly、Drawing 和类人建模。

Browser 子模块至少包含：

```text
session | document | featurescript | partstudio | assembly | drawing |
native_modeling | project
```

现有四级语义继续作为纵轴：

- L1 通用操作：locator/frame/键盘/等待/观测，不解释业务成功。
- L2 事务原子：一个 Onshape 用户意图，并拥有自己的验收证据。
- L3 工作流：组合多个 L2，完成一个零件、装配或工程图目标。
- L4 项目：fixture、assertion、checkpoint、resume 和跨对象编排。

### 5.3 主 MCP 初始暴露面

主 MCP 初始只暴露四个小型模块入口，名称暂定：

```text
mcp_documentation
mcp_featurescript
mcp_rest_api
mcp_browser
```

四个入口使用统一动作模型：

```text
overview | search | open | status | reset
```

公共参数限制为 `query`、条件必填的 `submodule`、可选 `semantic_level` 和 `limit`；
`limit` 默认 8、硬上限 12。模块有子模块时必须指定 `submodule`；叶节点模块可省略或
传入同名值。`overview` 只返回模块/子模块/层级摘要，`search` 只返回 bounded candidates，
`open` 才改变当前暴露视图。模块入口始终保留，确保随时可切换或 `reset`。

`semantic_level` 仅在显式传入时作为过滤条件；不写 L1-L4 时不得猜测默认等级，
而是返回所选子模块的全部语义级别，并包含未标等级的工具。`open(submodule=...)` 默认
暴露该子模块全部工具；若子模块本身过大，应继续细分子模块/能力族，而不是强迫调用方填 L。

Browser 模块首次打开时默认只暴露少量观测和 L3/L4 工具，例如：

```text
browser_session | browser_inspect | browser_watch | browser_catalog |
browser_build_part | browser_assemble | browser_draw_part | browser_run_project
```

L1/L2 只在 selector 调试、人工录制、事务实现、失败诊断或用户明确要求逐步建模时展开。
每次 `open/search` 最多新增 8-12 个工具，默认替换上一批候选，禁止无限累积。

### 5.4 注册表、语义目录与暴露视图分离

实现时必须保留三层，不得通过动态增删 `HANDLERS` 实现暴露：

```text
ALL_TOOLS / HANDLERS       完整能力和内部调用
          -> TOOL_CATALOG  语义元数据与查询索引
          -> EXPOSURE_VIEW 当前连接对模型可见的工具
```

`TOOL_CATALOG` 每项至少包含：

```text
name, module, submodule?, effectiveSubmodule, semanticLevel?, intent, keywords,
risk, confirmationRequired, dryRun, dependencies, schemaRef
```

规则：

- 外部 `tools/call` 只能调用模块入口或当前 `EXPOSURE_VIEW` 内工具。
- L3/L4 内部调用隐藏的 L1/L2 handler 不受暴露视图限制，但仍受确认、速率和验收门约束。
- 完整 schema 只在工具被暴露时进入 `tools/list`；搜索结果只返回名称和一句摘要。
- 目录加载时按模块注册表校验/归一化 `submodule`；叶模块的省略值与同名值必须等价。
- `semanticLevel` 缺失不能导致注册失败或调用拒绝；只有显式等级过滤时才排除未标级工具。
- 主 instructions 只保留路由、安全和“先索引后详情”规则，不列举完整工具目录。
- 暴露状态按 MCP 连接隔离，并在 `initialize`、断线重建和显式 `reset` 时恢复根视图。

### 5.5 动态工具列表与兼容模式

当前服务声明 `tools.listChanged: false`，`tools/list` 固定返回全部注册工具。动态模式需要：

- 将 capability 改为 `tools.listChanged: true`。
- `open/reset` 改变暴露视图后发送 `notifications/tools/list_changed`。
- 扩展 stdio/bridge 输出队列，使一次请求可以返回 response 并随后发送 notification。
- 验证客户端会重新请求 `tools/list`，并替换旧 schema，而不是把新旧定义永久累积。

不能假定所有 MCP 客户端都正确支持动态列表。必须同时提供：

```text
dynamic  list_changed 驱动的按需暴露
profile  启动时固定 module/submodule，可选 level；工具列表不再变化
gateway  四模块入口通过 describe/execute 代理长尾工具
static   调试和兼容用的完整 67+ 工具列表
```

推荐实施顺序是 `profile -> dynamic -> gateway fallback`。如果目标客户端不会替换旧工具
schema，动态模式不能提供严格的 token 上限，应优先使用 profile 或独立模块端点。

### 5.6 类人原生建模归属决策

首期将类人原生建模定义为 `browser.native_modeling` 子模块，而不是第五模块，也不是
第五级语义。理由是它继续复用 Browser mode 的 session、Playwright 输入、pacing、
confirmation、page object、selector、watch 和 checkpoint 基础设施。

它在现有四级语义中展开：

- L1：共享 click/type/press/wait/inspect/canvas 等浏览器原子，不重复注册一套。
- L2：创建草图、拉伸、圆角、阵列等单个特征事务；每次形成一个适合人工阅读的历史节点。
- L3：按明确顺序组合 L2，构造具有命名、顺序和局部验收的完整特征历史。
- L4：多零件、装配、工程图项目，支持 fixture/checkpoint/resume。

L2 原生特征事务至少返回：`featureCreated`、预期历史节点名、节点顺序/计数读回、
动作证据和失败原因。L3 不得只看点击结果；必须验证历史树、目标零件和必要几何状态。

只有满足以下任一条件时，才重新评估晋升为第五模块：

- 不再以 Browser/Playwright 为主要执行后端。
- 需要独立进程、session、权限、安全策略或部署生命周期。
- 大部分实现不再复用 Browser L1/L2。
- 需要独立版本、测试矩阵或对外协议。

### 5.7 分阶段任务与验收

#### Phase A：目录元数据与基线

- [ ] 为现有 67 个工具补齐必需的 module/intent/risk；有子模块的主模块必须补齐
  submodule，叶节点模块允许省略或填写同名值；semanticLevel 按适用性标注，允许为空。
- [ ] 建立模块注册表（含 `hasSubmodules`）和 submodule 归一化/条件必填测试。
- [ ] 生成并测试 `TOOL_CATALOG`；名称唯一、schemaRef 可解析、依赖无环或有明确允许边。
- [ ] 记录当前完整 `tools/list` 的工具数、JSON 字节数和估算 token，作为优化基线。
- [ ] 增加 bounded `catalog search/describe`，禁止一次返回完整目录和全部 schema。

#### Phase B：固定 profile

- [ ] 支持按 `module[:submodule][:level]` 启动的 exposure profile；level 可省略，
  省略时包含该子模块全部等级和未标级工具。
- [ ] 保持内部完整 handler 注册，高层组合隐藏低层工具的测试必须通过。
- [ ] 为四模块、Browser 子模块和可选 L1-L4 过滤建立 profile 测试；验证不传 level
  返回整个子模块，并确认真实 REST 默认仍关闭。
- [ ] 证明 profile 模式下初始 schema 体积相对完整模式显著下降。

#### Phase C：主 MCP 与动态暴露

- [ ] 实现四个固定模块入口和连接级 `EXPOSURE_VIEW`。
- [ ] 实现 `listChanged` capability、notification 队列和 tools/list 过滤。
- [ ] 外部调用未暴露工具时返回结构化拒绝；内部 L3/L4 调用不被误拦截。
- [ ] 测试 open/search/reset、模块切换、断线重连、Windows bridge 常驻和并发隔离。
- [ ] 对 DSH Web GUI 及计划支持的其他客户端做兼容矩阵；不支持时自动降级 profile/gateway。

#### Phase D：`browser.native_modeling`

- [ ] 先通过 `browser_watch` 和只读 DOM 扫描建立特征工具栏、dialog、历史树证据。
- [ ] 建立首批 L2 特征事务，优先草图、拉伸、圆角/倒角、阵列和布尔。
- [ ] 每个事务具备 dry-run、确认门、失败停止和历史树读回，禁止 click-level false success。
- [ ] 建立一个 L3 类人建模 fixture，验证特征名称、顺序、零件结果和可恢复失败。
- [ ] 建立 L4 项目 fixture，验证多零件、Assembly、Drawing 和 checkpoint/resume。
- [ ] 通过动态目录只暴露当前特征族，证明工具数量增长不会线性增加每轮上下文。

### 5.8 完成标准

该阶段只有同时满足以下条件才算完成：

- 根视图只含四模块入口，且始终可 reset。
- 任一模块/层级查询都 bounded，不读取完整生成索引或返回跨子模块的全部 schema。
- module 始终必填；有子模块时 submodule 必填；叶模块省略/同名 submodule 语义等价。
- 四级语义保持可选：不传 level 返回整个子模块，未标级工具不会注册失败或被禁止调用。
- 动态、profile、gateway/static 兼容边界有自动化测试和明确文档。
- 未暴露工具不能被外部绕过调用；内部组合、安全门和零 REST 默认不回归。
- 类人原生建模产生可读、可验证、可恢复的逐特征历史，而不是仅模拟一串点击。
- 完整模式仍可用于开发调试，但不再是普通会话默认值。

## 6. 安全/配额红线（沿用 CLAUDE.md）

- 浏览器工具全部 `estimated_api_requests: 0`，只动 UI，不碰 REST API。
- 浏览器只读探索阶段不点 `创建`/`删除`/`提交` 等会改变云端状态的按钮。
- 一旦开始点会改变数据的按钮（如 `提交`），必须走 dry_run 先确认，并记录在案。
