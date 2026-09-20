# 下载中心 target 卡死页面通道：根因与修复验收（2026-09-20）

本文记录一个**只有 0 次 Onshape REST 额度**的浏览器通道故障的根因链、代码修复与实机验收，
并区分两个容易被混为一谈的事实：**关闭请求被接受** 与 **目标消失**。

- 环境：Windows 常驻 Edge（`browser.resident = true`，`resident_port = 9333`），
  MCP 为普通 stdio 部署 `C:\MCP\onshapescript`，浏览器路径 0 REST 额度。
- 触发动作：`browser_export_step`（STEP 导出保存到本地）。
- 观测工具：`browser_get_page_tabs`、`browser_session(action="status")`、
  回环 CDP `/json/list`、`/json/close/<id>`。

## 1. 症状

STEP 导出之后，Edge 出现一个 `edge://downloads-hub/` target。只要它在，**所有页面级调用**
都以同样的方式失败：

```
MCP error -32001: downstream_timeout     # 约 32 s 后返回
```

`browser_get_page_tabs` 反复超时；同时 `browser_session(action="status")`
（只读、不附着页面）报 `sessionStatus: "uninitialized"`、`pages: []`，
`onshape_api_quota` / `bridge_control` 照常可用——即**通道级**故障，不是登录或云侧问题。

手工绕过曾有效：`/json/list` 找到该 target → `curl http://127.0.0.1:9333/json/close/<id>`。
但那只是绕过，导出下一次再跑就会重现。

## 2. 根因链

1. 页级事务开头调用 `BrowserSession._enforce_single_working_page`；
2. 它把 `context.pages` **原样**交给 `browser_common` 的
   `SyncSession.reconcile_pages`；
3. 该共享实现对**交给它的每一个页面**调用 `page.close()`（`_sync(page.close())`）；
4. 而对 `edge://downloads-hub/` 调 `page.close()` **永不返回**：Playwright 侧一直等，
   该 target 停留在 "closing" 状态。

于是每一个页级调用都会踩到这一步，超时后返回 `downstream_timeout`。
这不是"标签太多"，也不是 Onshape 侧慢。

## 3. 修复（`onshape_browser_mode/session.py`）

- 新增 `_BROWSER_INTERNAL_SCHEMES` / `_is_browser_internal_url()`：识别
  `edge://`、`chrome://`、`devtools://`、`brave://`、`vivaldi://`、`opera://`。
  `about:blank` **故意不算**内部页面（临时弹窗从它开始，必须仍可被正常清理关闭）。
- 新增 `_cleanup_candidates(pages)`，只返回 URL 可读且**非**内部页面的页面；
  `_enforce_single_working_page` 改为把这份清单交给 `reconcile_pages`。
  读不出 URL 的页面也被排除：对"只负责关页面"的例程，"无法判断"必须等于"别碰它"。
- 关闭内部页面改走回环 DevTools：`_close_browser_internal_page()`
  （`/json/list` 按 url 匹配 → `/json/close/<id>`），受 2 s socket 超时限制，
  **完全不经过 Playwright**。
- 回环端口只在 `browser.resident = true` 时才使用：`resident_port` 有默认值 9333，
  无此门禁时非常驻部署会向恰好监听该端口的**无关进程**发出关闭请求。
- `browser_export_step` 在 `download.save_as()` 之后立即请求关闭本次下载留下的内部页面
  （`_close_internal_download_pages`，全函数 guarded：上下文缺失或原生失败都不算导出失败）。

## 4. 验收

### 4.1 离线

- `dev/tests/test_browser_internal_pages.py`（内部页面分类、清理清单、DevTools 门禁与探测）、
  `dev/tests/test_browser_step_export.py`（导出后请求关闭且从不用 Playwright 关闭）：
  全部通过；全仓离线套件 **762 tests OK**（`PYTHONPATH=temp/browser-common-site`，
  `LIVE_API_ENABLED` 未设）。
- 测试全程不启动浏览器、不发 Onshape 请求、不真连回环 DevTools（该端点被 patch）。

### 4.2 实机

修复部署到 Windows 后（deployment `20260920T112900Z-downloads-hub-nonblocking`，3 个文件）：

| 观测 | 修复前 | 修复后 |
|---|---|---|
| `browser_get_page_tabs`（hub target 在列时） | `downstream_timeout` ~32 s | 立即返回标签列表 |
| STEP 导出 | 留下 hub target 并卡死通道 | 导出结果报告内部页面关闭请求 |

关键一条：修复后 `browser_get_page_tabs` 在 **`edge://downloads-hub/` 仍然出现在
`/json/list` 的情况下**照常秒回——即卡死的原因是"对它调用 Playwright `close()`"，
不是"它存在"。

## 5. 必须分清：接受请求 ≠ 目标消失

实测 Edge 会**接受**对 `edge://downloads-hub/` 的 `/json/close/<id>`（返回
`Target is closing`），但该 target **仍然留在** `/json/list` 里；先激活再关闭也一样。
即它实际上无法通过 CDP 删除，但已无害。

因此**不接受**把"被接受的关闭请求数"写成"已关闭页面数"。当前实现分开报告：

| 字段 | 含义 |
|---|---|
| `browserInternalPagesCloseRequested` | 被浏览器接受的关闭请求数（可能为 0） |
| `browserInternalPagesRemaining` | 仍在列的内部页面数；未探测或 DevTools 不可达时为 `null` |

（该字段最初名为 `browserInternalPagesClosed`，取值为当时那次导出的 1；同一时刻
`/json/list` 仍列出该 target，正是这次改名与拆分字段的依据。字段尚未发布，无外部消费者。）

改名字段后重新部署（deployment `20260920T113703Z-internal-page-fields`，9 个文件）并重启
节点（generation 33 → 34，`preservedClients: 2`、`reconnectRequired: false`），再做一次实机导出
`gridfinity-2x2-final-6` 复核：

```json
"browserInternalPagesCloseRequested": 1,
"browserInternalPagesRemaining": 1,
"apiRequests": 0
```

即**同一时刻**既报告"关闭请求被接受"，也报告"该内部页面仍在列"。紧随其后的
`browser_get_page_tabs` 秒回，而 CDP `/json/list` 仍列出
`edge://downloads-hub/` 与 Onshape 应用页两个 page target——通道健康与"目标未消失"
同时成立，正是本文要固定的区分。

`browserInternalPagesRemaining` 只在确实请求过关闭时才探测：没有请求就没有"重查"这件事，
否则每次导出都会多一次无关的 DevTools 调用，并让结果依赖运行环境。

## 6. 运维结论

- 页面通道卡死**不再需要**手工 `curl /json/close/...`，也**不需要**重启节点。
- `edge://downloads-hub/` 标签页可能仍**肉眼可见**地留在 Edge 里且删不掉；
  这不影响 MCP，不必处理，更不要为此重启桥或节点。
- 若将来页面级调用再次成片 `downstream_timeout`，先怀疑"某个页面被交给了
  `reconcile_pages` 且它的 `close()` 不返回"，而不是登录状态或额度。
