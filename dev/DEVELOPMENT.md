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

- UTF-8 协议修复；Windows 重启自愈（计划任务 `OnshapeMCPBridge`）。
- 本地 HTTP 代理支持（`browser.proxy_server`，当前 `http://127.0.0.1:10808`）。
- 常驻进程内 bridge + 浏览器登录态跨客户端保持。
- 启动清理残留标签 + 优先保留已登录页 + `lastAppUrl` 入口恢复。
- 只读探索工具：`browser_session` / `browser_watch` / `browser_inspect` /
  `browser_scroll` / `browser_click` / `browser_eval`。

## 4. 下一步计划

- [x] **selectors.py / actions.py**：稳定选择器与 Ace 读/写/提交动作已落地。
- [x] **第一个实质工具**：`browser_deploy_featurescript` 已实现并端到端验证
  （写 Ace → 提交 → 按钮 disabled 确认 → 读回校验 → 恢复原内容）。
- [ ] **page objects**：在 `onshape_browser_mode/` 下建 `pages/`，封装
  `DocumentsPage`、`FeatureStudioPage`（基于已扫描出的选择器）。
- [x] **只读操作工具**：`browser_open_document`、`browser_read_featurescript`
  已实现并实测（打开文档解析 did/wid/eid；读回 Ace 全文 + 页面 id）。
- [ ] **与 REST 模式打通**：浏览器拿到的 documentId/workspaceId/elementId 缓存进
  `onshape_rest_api_mode/config/onshape-state.json`，供 `onshape_rest_api_mode` 复用（仍是显式缓存，不隐式查询）。
- [ ] **人工录制验证**：用 `browser_watch` 录一次完整“打开文档→切 FeatureScript 标签→
  改代码→提交”流程，核对 `browser_click` 的选择器与真实操作一致。
- [x] **自愈脚本**：`mcp_main/bridge/windows/restart-bridge.bat` / `.ps1` 已落地——
  强杀自动化 Edge + 旧 bridge 后重启，强杀保留登录态。注：从 WSL interop
  调 Start-Process 不可靠（子进程随 interop 结束退出），请在 Windows 侧双击运行。
- [x] **上传+编译+建模闭环（0 配额）**：
  - 上传+编译：`browser_deploy_featurescript`（写 Ace → 提交 = 编译保存，读回 `verified`）。
  - 编译+建模验证：`browser_get_partstudio_features`（特征树出现 `Bc Branch cable trophy display`
    且零件数 132 → FS 编译成功且已实例化建模）。
  - 实测两个 Part Studio（`Cable trophy model v1` / `Cable trophy model validation`）均已实例化。
- [x] **标签管理工具（0 配额）**：
  - `browser_click` 增加 `button`（left/right/middle），右键打开上下文菜单。
  - `browser_rename_tab`：右键 → 重命名 → Playwright `fill` + `press("Enter")`。
  - `browser_delete_tab`：右键 → 删除（菜单项为 `ul.context-menu-list.context-menu-root`
    下的 `li.context-menu-item`），Playwright 真实点击（合成 `el.click()` 被 Onshape 忽略）。
  - 实测清理模块接口验证文档：12+ 个 Part Studio 收敛为 2 FS + 2 PS。

## 4.1 浏览器操作分层架构（未来计划）

将浏览器操作按语义自下而上分为四层；新增工具时先归类，逐层复用，禁止在高层工具里
内联低层按钮语义（选择器只允许出现在通用操作层与 `selectors.py`）。

1. **通用操作（原子）**：完全不涉及按钮语义——纯点击（含右键/中键）、双击、滚动、
   填写数值、按键、读取元素信息。现有：`browser_click`（+`button`/`double`）、
   `browser_scroll`、`browser_eval`、`browser_inspect`。
2. **低级语义（事务原子）**：由数个通用操作组合、绑定到具体 Onshape 事务，一般
   “按一个按钮 + 填写弹出要求输入的数值”。例：创建文档、修改文档名、复制/替换/删除
   FS 语段、导航到页面、重命名页面、导入自定义特征、编译 FS 脚本。
   现有：`browser_create_document`、`browser_create_tab`、`browser_rename_tab`、
   `browser_delete_tab`、`browser_open_document`、`browser_open_insert_feature_dialog`。
3. **高级语义（中型操作）**：多个低级语义之和。例：`browser_deploy_featurescript`
   = 打开/建 FS 标签 + 复制 FS 语段 + 编译 FS 脚本；再加可选参数“应用到指定
   Part Studio”即为“部署并应用”。现有：`browser_deploy_featurescript`、
   `browser_insert_custom_feature`、`browser_create_document_version`。
4. **顶级语义（脚本化建模项目）**：多个高级语义串成一条连续事务链；一个建模项目
   对应一个顶级语义，由该语义的一串事务直接完成建模。尚待实现（可作为预编排脚本）。

## 5. 安全/配额红线（沿用 CLAUDE.md）

- 浏览器工具全部 `estimated_api_requests: 0`，只动 UI，不碰 REST API。
- 浏览器只读探索阶段不点 `创建`/`删除`/`提交` 等会改变云端状态的按钮。
- 一旦开始点会改变数据的按钮（如 `提交`），必须走 dry_run 先确认，并记录在案。
