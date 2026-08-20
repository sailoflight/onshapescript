# 开发经验与计划（browser 自动化线）

> 本文档记录开发过程中的关键决策、踩坑与下一步计划。使用经验（页面结构、
> 选择器、工具用法）见 `dev/experience/browser-usage-notes.md`。

## 1. 架构决策（已落地）

- 四包结构：`mcp_main`（MCP 协议/工具注册）、`onshape_docs`（离线文档）、
  `onshape_rest_api_mode`（REST API，配额保护）、`onshape_browser_mode`（浏览器自动化）。
- 浏览器只在 Windows 跑；Linux 只保留 stdlib 中继，不装 Playwright。
- `bridge_server.py` 从“每连接拉子进程”改为**常驻进程内 dispatch**：Onshape
  关浏览器即登出，浏览器必须存活于跨客户端重连的常驻进程里。
- 单工作页规则统一收口在 `BrowserSession._enforce_single_working_page()`。

## 2. 开发踩坑记录（重要）

1. **中文 Windows GBK 崩溃**：`tools/list` 响应里的 `⚠` 无法用 GBK 编码写 stdout，
   子进程 rc=1 且无响应。修复：`serve()` 直接读写 `sys.stdin.buffer/stdout.buffer`
   的 UTF-8 字节流。
2. **Playwright sync API 线程绑定**：bridge 每个客户端一个线程时，第二个客户端的
   `page.evaluate()` 报 `Target page, context or browser has been closed` 并误走
   重启浏览器路径，反复 spawn `about:blank`。修复：单客户端规则下主线程串行 serve。
3. **SPA URL 误判登录**：`domcontentloaded` 后立即读 URL 会误报已登录；等 4s
   路由稳定后按最终 URL 判定。
4. **优雅关闭 vs 强杀**：`context.close()` 触发 Onshape 登出；`Stop-Process -Force`
   保留会话文件 → 下次自动恢复。重启流程必须强杀，不能优雅关闭。
5. **多标签漂移**：人工登录常在新标签完成。`start()`/`status()` 必须遍历
   `context.pages` 优先选已登录应用页，并关闭其余标签。

## 3. 已完成（git 链）

- UTF-8 协议修复；Windows 重启自愈（计划任务 `OnshapeMCPBridge`）。
- 本地 HTTP 代理支持（`browser.proxy_server`，当前 `http://127.0.0.1:10808`）。
- 常驻进程内 bridge + 浏览器登录态跨客户端保持。
- 启动清理残留标签 + 优先保留已登录页 + `lastAppUrl` 入口恢复。
- 只读探索工具：`browser_session` / `browser_watch` / `browser_inspect` /
  `browser_scroll` / `browser_click` / `browser_eval`。

## 4. 下一步计划

1. **page objects**：在 `onshape_browser_mode/` 下建 `pages/`，封装
   `DocumentsPage`、`FeatureStudioPage`（基于已扫描出的选择器）。
2. **按钮语义映射**：把 `dev/button-map/scan-*.json` 转成
   `onshape_browser_mode/selectors.py` 的稳定 selector 常量。
3. **只读操作工具**：基于 page objects 增加 `browser_open_document`、
   `browser_get_featurestudio`、`browser_read_featurescript` 等 0 配额的只读工具。
4. **与 REST 模式打通**：浏览器拿到的 documentId/workspaceId/elementId 缓存进
   `config/onshape-state.json`，供 `onshape_rest_api_mode` 复用（仍是显式缓存，不隐式查询）。
5. **人工录制验证**：用 `browser_watch` 录一次完整“打开文档→切 FeatureScript 标签→
   改代码→提交”流程，核对 `browser_click` 的选择器与真实操作一致。
6. **自愈脚本**：把“强杀 bridge + 强杀 Edge + 重启 + 恢复登录”固化成
   `tools/windows/restart-bridge.bat`，避免手工 PowerShell。

## 5. 安全/配额红线（沿用 CLAUDE.md）

- 浏览器工具全部 `estimated_api_requests: 0`，只动 UI，不碰 REST API。
- 浏览器只读探索阶段不点 `创建`/`删除`/`提交` 等会改变云端状态的按钮。
- 一旦开始点会改变数据的按钮（如 `提交`），必须走 dry_run 先确认，并记录在案。
