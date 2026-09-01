# 浏览器自动化使用经验（Onshape Windows 宿主）

本文档是 2026-08-20 起对 Onshape 浏览器自动化探索的**使用经验**沉淀，供后续
开发 page objects / selector 映射 / 自动化脚本时直接复用。所有结论都来自
真实 Edge（channel=msedge）+ 持久化 profile 的实测，0 次 Onshape API 调用。

## 1. 运行模型

- 普通 MCP 与浏览器运行在同一宿主（当前实测宿主为 **Windows**）；跨宿主客户端通过独立安装的 `win-wsl-mcp-bridge` 连接。
- 项目源码入口是 `python -m mcp_main.win.mcp`。共享桥若需要跨客户端重连保持会话，必须在其自身生命周期契约中保持同一 MCP 进程并禁止 profile 多 owner；本仓库不再实现 relay/listener。
- 单客户端铁律 + **单工作页铁律**：`session.start()` 每次只保留一个工作页，其余标签全关
  （`_enforce_single_working_page`）。
- 关闭方式决定登录态：**强杀进程保留登录，优雅关闭会登出**。Onshape 无“保持登录”。

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
| `browser_session` | 登录态/页面状态 | `action=status|login` |
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
`semantic_levels=["L3"]`，再通过 `browser_invoke_discovered` 按返回 schema 调用；不
要求额外 `intent` 参数。gateway 不绕过确认、成本或 handler 验收。未分类工具继续
有效并默认可见；`ONSHAPE_MCP_TOOL_EXPOSURE=static` 保留完整列表兼容模式。当前审阅
元数据和非阻断 lint 在
`onshape_browser_mode/semantics.py`。

### 3.2 连接级动态展示约定

`mcp_tool_view` 的 profile/semantic-level 只缩小当前连接返回的 `tools/list`，不修改
完整 registry，不拒绝已知工具名，也不改变确认、quota、pacing 或验收门。正确流程是：
Operator 以 `ONSHAPE_MCP_TOOL_EXPOSURE=dynamic` 启动；client 在 initialize 中确认
`tools.listChanged=true`；agent 先 `status`，再 `set`；client 收到
`notifications/tools/list_changed` 后重新请求并**替换** `tools/list`，不能在旧列表上追加。
`reset` 回到该连接启动时的 profile；重新连接创建独立的新 view。

窄化 browser semantic levels 时必须常驻 `browser_session`、
`browser_discover_tools` 和 `browser_invoke_discovered`，否则 agent 难以观察、继续发现或
恢复视图。重复设置同一 view 不发 notification。客户端不支持 listChanged 时继续使用
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
  - 编译状态由 Ace `editor.session.getAnnotations()` 读取；`browser_get_fs_compile_status`
    归一化为 `compiled/errors/annotationCount`。部署只有在提交按钮从 enabled 变为
    disabled、源码精确回读且注解为空时才返回 `deployed:true`。
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
- `browser_reconnect` 会检测并点击该链接恢复会话；`browser_open_document` /
  `browser_read_featurescript` / `browser_deploy_featurescript` 在执行前自动重连。
- 实测：点击后弹窗消失，页面回到原文档 URL。

### 4.4 Part Studio 页与「添加自定义特征」对话框

- Part Studio 标签 URL 的 elementId 与 FS 标签不同（`0c7862642d02c53c3dd7cd79`）。
- 特征树：`.features-title`（「特征 (5)」）、`.os-list-item`；
  自定义特征 `.os-list-item.ns-user-feature`（如 `Bc Branch cable trophy display`），
  默认几何图元 `.os-list-item.ns-default-feature`。
- 零件列表：`.part-list-container`（`零件数 (132) base ...`）——自定义特征出现且
  零件数>0 即 0 配额的「编译+建模」验证。
- 工具栏：`.toolbar-item`，按钮 `.tool.is-activatable.is-button`；文字标签
  `.tool-label.hide-in-toolbar` 是**隐藏的**，`browser_click(text=...)` 点不到，
  要按 `.toolbar-item` 的 textContent 找到后点内部按钮。
- 「添加自定义特征」对话框 `.feature-studio-insert-dialog`：
  - 标签 `.os-dialog-tab`：`当前文档` / `其他文档`；
  - 文档名 `.select-item-dialog-document-name`；
  - 若提示「没有可用的特征。… 创建一个版本」，说明 Feature Studio 未发布版本，
    需先在文档里创建版本后自定义特征才可插入。

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
6. 实测：dry_run 纯本地预览（不启动浏览器）→ 部署修改（23907 字符，`verified:true`）→
   恢复原内容（23875 字符，`verified:true`）。

关键 JS（`actions.py`）：
- 读全文：`ed.getValue()`
- 写全文：`ed.setValue(text); ed.clearSelection(); ed.moveCursorTo(0,0)`
- 提交按钮：`.tool.is-activatable.os-primary.is-button`，文案「提交」，
  `className.includes('disabled')` 表示无未提交改动。

## 6. 已知坑

- 多标签漂移：人工登录可能在新标签打开 documents，旧 signin 标签仍残留。`status()`/`start()`
  会遍历 `context.pages` 优先选已登录应用页，并关闭其余标签。
- Playwright sync API 绑定创建线程；桥接必须**主线程串行**处理客户端，否则报
  `Target page, context or browser has been closed`。
- `launch_persistent_context` 命令行末尾固定带 `about:blank`，这是正常启动页；
  是否恢复上次标签取决于上次是否强杀（崩溃恢复）。
- 中文 Windows 下 Python stdout 默认 GBK；MCP 协议读写必须走 UTF-8 字节流。

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
- 工程图加载慢：`正在加载工程图…` 长时间不消失时可 `browser_reload`（或
  `location.reload()`）刷新；若源 Part Studio 已被删除，工程图会一直卡在加载。


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
  view selector 返回 0；`browser_drawing_insert_views` 因此还要求恰好一个新 tab，
  并解码 main-canvas PNG，排除图框/标题栏后检查主体墨迹比例和空间集中度。
  实测 1240×694 fixture 中有四个投影视图，证据图为
  `dev/button-map/scan-drawing-four-views.png`。不可见的 preview/drawer 候选仍标记
  unverified，读取工具返回结构化 absence/unknown。
