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

## 4. 下一步计划（非分层项）

- [ ] **page objects**：在 `onshape_browser_mode/` 下建 `pages/`，封装
  `DocumentsPage`、`FeatureStudioPage`、`PartStudioPage`、`AssemblyPage`、
  `DrawingPage`（基于已扫描出的选择器与 iframe 结论）。
- [ ] **与 REST 模式打通**：浏览器拿到的 documentId/workspaceId/elementId 缓存进
  `onshape_rest_api_mode/config/onshape-state.json`，供 REST 模式显式复用（不隐式查询）。
- [ ] **人工录制验证**：用 `browser_watch` 录一次完整“打开文档→切 FS 标签→改代码→
  提交”流程，核对 `browser_click` 选择器与真实操作一致。

## 4.1 四大语义分层：现存工具归档 + 待开发计划

新增工具时先归类、逐层复用；禁止在高层工具里内联低层按钮语义（选择器只允许出现在
通用操作层与 `selectors.py`）。标记：✅ 已落地并实测、🔜 本次任务证明应开发。

### 1) 通用操作（原子，零按钮语义）

纯点击/右键/中键、双击、滚动、填值、按键、读取元素信息、等待、刷新、跨框架访问。

现存归档：

- ✅ `browser_click`（`button` / `double` / `modifiers`）：右键开上下文菜单、Ctrl 多选。
- ✅ `browser_scroll`、`browser_inspect`、`browser_eval`（主框架 JS）。
- ✅ `browser_reload`（等待过久刷新；工程图加载卡死场景催生）。
- ✅ `browser_session`（会话/登录态读）、`browser_watch`（人工录制观察，读性质）。

待开发：

- 🔜 `browser_wait`（条件等待）：等元素出现/消失/文本变化或网络静默，替代硬编码
  `wait_for_timeout`；慢代理与“正在加载工程图…”轮询证明固定延时不可靠。
- 🔜 `browser_press_key` / `browser_type`：真实键盘输入（Playwright `press`/`type`）；
  重命名标签、工程图标注输入等场景合成 `dispatchEvent` 无效。
- 🔜 frame-aware 操作（`frame_url` 参数作用于 eval/click/scroll）：工程图编辑器在
  跨域 `production-drawing-*.onshape.com` iframe 内，须用 `page.frames` 按 URL
  匹配目标 frame 再定位（本次尺寸标注被同源策略卡住的根因）。

### 2) 低级语义（事务原子，数个通用操作之和）

绑定到具体 Onshape 事务，“按一个按钮 + 填弹出数值”。

现存归档：

- ✅ `browser_create_document` / `browser_open_document` / `browser_reconnect`。
- ✅ `browser_create_tab`（Feature Studio / Part Studio / Assembly / Drawing；
  创建项是常驻隐藏 `a.dropdown-item`，JS 点击即可）。
- ✅ `browser_rename_tab` / `browser_delete_tab`（右键菜单，须真实 Playwright 点击）。
- ✅ `browser_get_page_tabs`（列标签）/ `browser_get_partstudio_features`（读特征树与零件数）
  / `browser_read_featurescript`（读 FS 全文）——事务级读取。
- ✅ `browser_open_insert_feature_dialog`（只读开对话框）。

待开发：

- 🔜 `browser_insert_assembly_instances`：装配体“插入零件和装配体”对话框多选
  Part Studio 并确认（本次用 `browser_eval` 临时拼装，应固化）。
- 🔜 `browser_fix_instances` / `browser_group_instances`：固定/分组选中装配实例
  （本次用右键菜单“固定”完成刚性连接；工具栏另有“分组”需真实多选）。
- 🔜 `browser_create_drawing`：从指定 Part Studio/Assembly 创建工程图标签并选模板。
- 🔜 `browser_add_drawing_dimension`：工程图内点标注工具→点几何→放置尺寸；
  依赖 frame-aware 通用操作。
- 🔜 `browser_delete_element`（按元素 id 删除）：当前只能按标签名删除；重建 Part
  Studio 后旧工程图源引用悬空，需按元素 id 清理悬空引用。

### 3) 高级语义（中型操作，多个低级语义之和）

现存归档：

- ✅ `browser_deploy_featurescript`（打开/建 FS 标签 + 写 Ace 全文 + 提交编译 + 读回校验）。
- ✅ `browser_insert_custom_feature`（工作区下拉按条目点击，非容器）。
- ✅ `browser_create_document_version`（当前文档页签上建版本）。

待开发：

- 🔜 `browser_deploy_and_apply_featurescript`：deploy + 可选 apply 一体化
  （参数 `feature_name`、`part_studio_name`、`confirm`）。本次反复
  “部署→切 PS→点下拉→点条目→点 OK→读零件数”证明需要固化。
- 🔜 `browser_build_part`：新建/复用 Part Studio + 应用特征 + 读回 `零件数 (N)`
  与零件名，输出 `{parts, partNames}` 作为建模成功判定（本次验收标准）。
- 🔜 `browser_assemble`：建装配体标签 + 插入指定实例 + 固定/分组，返回实例树。
- 🔜 `browser_draw_part`：建工程图 + 选源 + 加基础尺寸标注，返回图框/视图状态。

### 4) 顶级语义（脚本化建模项目，一个项目对应一个脚本）

预编排脚本，由高层语义串成连续事务链；LLM 只传项目参数，不再逐步点击。

- 🔜 `browser_run_project(project="module-interface-verification")`：
  内部读取 `dev/fixtures-capture/<project>.json` 的步骤清单与断言，串行执行：
  1. `create_document` → 2. `deploy_featurescript(PartA)` + `deploy_featurescript(PartB)`
  → 3. `build_part(A)` + `build_part(B)` → 4. `assemble([A,B])` → 5. `draw_part(A/B)`
  → 6. 断言 `零件数 (1)`、实例树、图框存在。
- 失败在某步时返回已完成的步骤序号与状态，支持断点续跑。
- 顶级语义不暴露 UI 选择器；选择器只存在于通用操作层与 `selectors.py`。

### 分层依赖总则

```
顶级语义 ──> 高级语义 ──> 低级语义 ──> 通用操作 ──> selectors.py / page.frames
   (脚本)      (中型流程)     (事务原子)     (原子动作)
```

- 每层**禁止调用上层**；但可以调用**任意下层**（跨多层调用允许）。例如高级语义可直接复用
  低级语义与通用操作，顶级语义可直接编排高级/低级/通用操作。反向（下层依赖上层）才是设计错误。
- 新发现的选择器/iframe/等待结论统一沉淀进 `selectors.py` 与
  `onshape_docs/experience/browser-automation.md`，工具只引用常量。

## 5. 安全/配额红线（沿用 CLAUDE.md）

- 浏览器工具全部 `estimated_api_requests: 0`，只动 UI，不碰 REST API。
- 浏览器只读探索阶段不点 `创建`/`删除`/`提交` 等会改变云端状态的按钮。
- 一旦开始点会改变数据的按钮（如 `提交`），必须走 dry_run 先确认，并记录在案。
