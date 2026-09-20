# FeatureScript 通知检索修复实测（2026-09-20）

本页记录两件在同一条建模路径上实测出来的事：

1. **检索缺陷**：`browser_get_fs_compile_status()` / `browser_fs_capture_diagnostic()`
   会静默漏掉 Part Studio 的重生成错误——本页给出它漏在哪、修成什么、以及修好之后的实测读。
2. **附带发现的建模缺陷**：同一个模型的磁铁孔被摆到板外（16 个孔里 7 个落空），
   而特征树当时是"零错误、水密、尺寸正确"。它是被几何包的质心抓出来的。

## 范围与安全

- 全程**只走浏览器腿**：`browser_*` 工具 + 本地文件，`apiRequests: 0`，
  `LIVE_API_ENABLED` 未启用，Onshape REST 年度额度账本没有变化。
- 目标文档：`1ef2be8f3d45e6f996af24ab` / workspace `bac7c0bf31912a956c44d15a`；
  Part Studio `f0360bb015d7612284423f55`，Feature Studio `c57b7cc5f7291694afffd17b`。
- 云端变更只有两类，都由用户的任务授权：Feature Studio 源码提交（提交 ≠ 新增特征行）
  与 STEP 导出（导出对话框下载，不计 REST 额度）。
- 运行时是 `/mnt/c/MCP/onshapescript`（Windows 裸 stdio MCP 的文件复制部署）。
  本轮涉及两次纯数据部署：`20260920T102123Z-gridfinity-magnet-hole-frame-fix`、
  `20260920T103101Z-gridfinity-refresh-fixture`；onshape 节点为 generation 27，
  浏览器腿的代码变更更早一轮已经部署并在本轮生效。

## 缺陷：报错被静默丢弃

用户原话："这个报错获取要修复"。当时的实测现象是：
`browser_get_fs_compile_status()` 返回 `noticeCount: 0`、`compiled: true`，
而 Part Studio 里明明有一行特征在报错。用户的补充线索："现在发现 FS 通知也会报告重生成
错误 但是是 log 登记"。

定位过程不靠猜测，而是在采集器里加了**有界结构证据**（`noticePaneStructure`：静默容器
摘要 + 关键词过滤后的 pane class 名）后直接读出来的。结论是三处叠加：

1. **跨元素被跳过**：采集器里有一句 `if (activeTabName && tabName && tabName !==
   activeTabName) continue;`，别的文档元素的通知直接丢掉。
2. **过期容器被跳过**：Part Studio 的容器带 `notices-out-of-date` 类名，采集器因此整个
   跳过它——而真正的 error 就躺在这个容器里一张普通的
   `.compact-table.feature-script-notice-table` 内（`.notice-location-message` /
   `-line-number` / `-column-number` + `.error-text-td` / `.error-list-error-text`）。
3. **严重级被降级**：严重级原先看标题图标，于是同一张表里的 error 被记成 `info`。

## 修复

| 位置 | 改动 |
|---|---|
| `onshape_browser_mode/actions.py` | `FS_NOTICE_SNAPSHOT_JS` 不再按标签过滤、不再跳过过期容器；每条通知带 `tabName` / `isActiveTab` / `outOfDate`；新增 `activeTabName`、`containerCount/Titles`、`noticeCount`、`activeTabNoticeCount`、`otherElementNoticeCount`，以及静默容器存在时的 `noticePaneStructure` / `unstructuredContainers` / `paneClassNames`（都做了条数上限）。严重级改为：表 className 与全部后代 class 名里出现 `error` 即 `error`，否则 `warn`→warning、`info`→info，都没有再退 warning |
| `onshape_browser_mode/actions.py` | `read_featurescript_compile_status()` 只把**活动标签的新鲜通知**算进 `errors` / `compiled` / `errorCount`（部署门因此保持不变），另给 `activeTabName`、`activeTabNoticeCount`、`elementNotice*`、`elementError*`、`staleNotice*`、`staleError*`、`documentClean`、`noticeContainerTitles`、`elementDiagnosticSummary` / `staleDiagnosticSummary` |
| `onshape_browser_mode/diagnostics.py` | `_server_conclusion()` 增加 `documentClean`、`elementErrorCount`、`staleErrorCount`（纯增加，`DIAGNOSTIC_SCHEMA_VERSION` 仍为 1） |
| `mcp_main/win/mcp/browser_tools.py` | `browser_fs_capture_diagnostic` 返回 `documentClean`、`elementErrorCount`、`elementNotices`、`staleErrorCount` |
| `mcp_main/win/mcp/server.py` | `browser_deploy_featurescript` 结果增加 `documentClean`、`elementNoticeCount`、`elementErrorCount`、`elementErrors`、`staleErrorCount` |

`documentClean` 的定义是"没有 Ace annotation error、没有任何元素的 error、没有过期容器的
error，且这次读取是完整的"——读不到通知面板时它**不会**报 clean。

## 实测证据（浏览器腿，0 REST）

**读到了别的元素里的重生成错误（修复前读不到的那种）。** 当时 Feature Studio 是活动标签，
`browser_get_fs_compile_status()` 返回的 error 是：

```
text      : throw Plate width is not an integer multiple of the cell pitch; expected a Gridfinity plate
stack     : Feature Studio 1 (gfCellCount) -> (const gfSocketPockets)
            -> onshape/std/feature.fs (defineFeature) -> Part Studio 1 (GF Socket Pockets 1)
location  : line 100 / 107, column 9
tabName   : "Part Studio 1"   isActiveTab: false   outOfDate: true
elementErrorCount: 1   staleErrorCount: 0   documentClean: false
compiled  : true            noticeReadComplete: true
```

即：**活动标签的 Ace 是干净的（`compiled: true`），错误在另一个元素里，而它带着
`notices-out-of-date` 标记**——两个跳过条件正好同时命中它。

**修好模型后的干净读。** 重新提交修正后的 Feature Studio（见下节），再读：

```
noticeContainerTitles: ["Part Studio 1"]
unstructuredContainers: [{tabName: "Part Studio 1", outOfDate: true,
                           text: "监控\n  Part Studio 1\nResult: Regeneration complete"}]
noticeCount: 0  elementNoticeCount: 0  elementErrorCount: 0  staleErrorCount: 0
documentClean: true   noticePaneOpenedForRead: true   noticePaneRestored: true
```

容器此时没有通知表，只有一句 `Result: Regeneration complete`；采集器把它记进
`unstructuredContainers`（有界结构证据）而不是当成通知，也没有因此谎报错误。

## 附带发现的建模缺陷：磁铁孔摆到了板外

同一轮的几何终检暴露出质心不对称，顺着查出了一个**与检索无关**的建模错误，因为它是
"零错误模型也可能是错的"这条结论的直接证据，所以一并记录。

| 指标 | 修改前 | 修改后 |
|---|---|---|
| 质心 x, y (mm) | -0.205846211, -0.205846626 | **0.000114, 0.000011** |
| 质心 z (mm) | 3.506100101 | 3.499408 |
| 体积 (mm³) | 36628.552775144 | 36011.474513942 |
| 三角面 | 30940 | 39456 |
| 尺寸 / 水密 | [84, 84, 10] / true | [84, 84, 10] / true |
| 孔位 x (mm) | {-13, 13, 29, 55} | {-34, -8, 8, 34} |

- 质心基准：同一分析器对**未切割**的板体给出 `[-0.0, 0.0, 5.0]`，所以 0.206 mm 不是
  分析器的偏差。
- 根因：磁铁孔沿用了"格心"含义的 `firstCell` 变量，却套用参考实现的"格角"公式
  `firstCell + {d, pitch - d}`。84 mm 板上 x=55 已在板外，16 个孔里 7 个落空，
  剩下的又切错了位置（多挖了 +x/+y 侧，质心因此被推向 -x/-y）。
- 修正为 `firstCell ± (cell_pitch / 2 - magnet_from_side)`，并加了
  `holeInset <= 0` 的 `regenError` 守卫。
- 体积减少 617 mm³，与"7 个原本落空的孔真正挖掉的料"同量级，第二个独立通道再次印证。
- 两者的完整数值来源：
  `outputs/step_exports/gridfinity-2x2-final-1|2/step-manifest.json` 与
  `outputs/geometry_packages/gridfinity-2x2-final-1|2/report.json`
  （STEP sha256：`aa4399a5…` → `4fc8075e…`）。

## 修正后的模型状态（活证据）

- 特征树 `特征 (7)`：默认几何图元 + Origin/Top/Front/Right +
  `GB GF Base Plate Body 1` + `GS GF Socket Pockets 1` + `GM GF Magnet Holes 1`，
  三行全部 `hasError: false`；`零件数 (1) Gridfinity baseplate 2x2`。
- 云端 Feature Studio 源码 = 仓库文件：
  `sourceSha256 40d1064bd758bee155786c2d5a86be2a82fc99f9094b2c7ef4339b8051c9cbc2`，
  24534 字节 / 515 行，与 `sha256sum dev/fixtures-capture/gridfinity-baseplate.fs` 一致。
- 修正通过**只提交、不加行**的方式生效：`dev/fixtures-capture/gridfinity-refresh-fs.json`
  单步项目（`apply: false`）提交 Feature Studio，工作区里已插入的三行随之重算，
  特征树仍是三行。项目运行器会把这步报成失败（缺 `built` 键），但同一结果里
  `deployed` / `verified` / `commitAccepted` / `compiled` 均为真。

## 离线验证

- `python3 dev/tests/test_fs_notice_collector.py`：25 个用例，在 node + stub DOM 下执行
  **同一份生产字符串**。
- 全量离线套件 `PYTHONPATH=temp/browser-common-site python3 -m unittest discover -s
  dev/tests`：**723 tests OK**。
- `python3 onshape_docs/scripts/fs_local_check.py dev/fixtures-capture/gridfinity-baseplate.fs`：PASS。

## 边界（不声明的东西）

- `messages`（一个通知表含多个 `.notice-location-message` 段落）仍只有 stub DOM 证据；
  本次实机记录里每张表都只有一段。
- `documentClean: true` 只表示"这次读取没看到 error"；它依赖采集器真的读到了通知面板
  （`noticeReadComplete`），读不到时会退化为不 clean，而不是"没有错误"。
- 磁铁孔的修正只由"质心 + 体积 + 面数 + 重生成无错"证明；**没有**做截面/视觉复核，
  孔与型腔底面的实际间隙没有量测。
- 本轮没有清理迭代过程中产生的多余文档；文档删除是另一个（破坏性）动作。

## 复现

1. 离线：`python3 dev/tests/test_fs_notice_collector.py` 与全量套件；
2. 实机（浏览器腿，0 REST，需要操作者在场处理登录/会话）：
   `browser_get_fs_compile_status` → 期望 `noticeContainerTitles` 含非活动元素、
   `documentClean` 与实际一致；
3. 重提交并复核：
   `browser_run_project(project="gridfinity-refresh-fs", confirm_mutation=true)`
   → `browser_activate_tab(name="Part Studio 1", content="partstudio")`
   → `browser_get_partstudio_features`（三行 `hasError: false`、`零件数 (1)`）
   → `browser_export_step` + `browser_build_geometry_package`（质心应回到原点、
   `watertight: true`、`dimensionsMm [84, 84, 10]`）。
