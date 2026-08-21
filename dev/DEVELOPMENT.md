# 开发经验与计划（browser 自动化线）

> 本文档只记录开发决策与计划。可复用的页面结构、选择器和工具经验见
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

## 5. 安全/配额红线（沿用 CLAUDE.md）

- 浏览器工具全部 `estimated_api_requests: 0`，只动 UI，不碰 REST API。
- 浏览器只读探索阶段不点 `创建`/`删除`/`提交` 等会改变云端状态的按钮。
- 一旦开始点会改变数据的按钮（如 `提交`），必须走 dry_run 先确认，并记录在案。
