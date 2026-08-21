# 浏览器自动化使用经验（Onshape Windows 宿主）

本文档是 2026-08-20 起对 Onshape 浏览器自动化探索的**使用经验**沉淀，供后续
开发 page objects / selector 映射 / 自动化脚本时直接复用。所有结论都来自
真实 Edge（channel=msedge）+ 持久化 profile 的实测，0 次 Onshape API 调用。

## 1. 运行模型

- 浏览器只在 **Windows** 上跑，Linux 只跑 `mcp_main/bridge/mcp_tcp_bridge.py` 做 stdio↔TCP 中继。
- Windows 常驻 `mcp_main/bridge/bridge_server.py`，**进程内直接 dispatch MCP**，不在每个连接拉起子进程。
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
- FeatureScript 悬浮文档：`.os-feature-script-doc-popup-layer`（当前显示
  `LengthBoundSpec type A spec to be used with the isLength pre...`）。
- 每个标签都有「监控 / 配置文件」菜单：`.os-menu-tool`（文本形如 `监控 Cable trophy model v1`）。

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
