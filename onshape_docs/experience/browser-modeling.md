# 浏览器零 REST 配额 FeatureScript 建模工作流

这是 2026-08-20 后多轮浏览器实测合并出的当前规范流程：在**新建文档**
里完成「创建 Feature Studio → 部署源码 → 创建版本 → Part Studio 应用自定义
特征 → 验证零件」，不污染生产文档，全程 0 次 Onshape REST API。历史记录中
“待实现”或“仅插入即完成”的中间结论已被后续实测替代，不再作为独立指南。

## 1. 已实测跑通的步骤

| # | 步骤 | 工具/选择器 | 实测结果 |
|---|---|---|---|
| 1 | 创建新文档 | `browser_create_document(name)`：`#create-new-type` → `.create-new-document` → `#document-name-input` 填名 → `.new-document-dialog .btn-primary` | `fs-modeling-test`，did `4774246bad5e29f4c98bf632`，wid `721b2be4e4dceb696e8576e1` |
| 2 | 新建 Feature Studio 标签 | 隐藏的 `a.dropdown-item`「创建 Feature Studio」→ JS click | 标签 `Feature Studio 1`，eid `b08754f2be050e1c13a6bdf8` |
| 3 | 部署 FS 源码 | `browser_deploy_featurescript(script)`：写 Ace → 点「提交」 | 81→23875 字符，`deployed:true, verified:true` |
| 4 | 创建版本 | 插入对话框「当前文档」→ 提示「没有可用的特征。… 创建一个版本」→ `.select-item-prompt-save-version a` → `.version-or-workspace-dialog` → **取消勾选** `.publish-custom-features-checkbox` → 点「创建」 | 版本 `V1`，对话框显示特征可用 |
| 5 | 插入特征 | 插入对话框特征行 `.select-item-dialog-item-row.child-item-container` **双击**（`os-double-click=selectChildInsertableThenClose`） | 特征进入特征树，`feature-id` 已存在 |

## 2. 关键机制（易错点）

- **插入 = 双击，不是「插入」按钮**：对话框底部 `.standard-content-insert-button` 实际尺寸为
  `[0,0,0,0]`（不可点）。特征行有 `os-single-double-click` 指令：
  - 单击 `os-click=selectChildInsertable` → 只选中（`os-selected`）；
  - **双击** `os-double-click=selectChildInsertableThenClose` → 选中并关闭对话框 = 插入。
- **版本 ≠ 发布**：`version-or-workspace-dialog` 勾选「发布自定义特征」后按钮变为
  「创建和发布」，但发布有额外硬要求（公开文档、PDF、FeatureScript 说明、已在 Part Studio
  使用等）。仅插入本机文档只需**不勾选发布**直接「创建」。
- 工具栏「添加自定义特征」的文字标签 `.tool-label.hide-in-toolbar` 隐藏，需按
  `.toolbar-item` 的 textContent 找到后点内部 `.tool.is-button`。
- 代理网络慢：文档/标签/对话框加载都慢，每个导航后要轮询等待目标元素出现，不要固定短等待。

## 3. 关键修正：Part Studio 需要「应用」特征

之前走「添加自定义特征」对话框双击只会产生 `not-computed` 行（`零件数 (0)`）。
正确流程是**手动应用**：

1. 点工具栏按钮 **`此工作区中的自定义特征`**（`.tool[title="此工作区中的自定义特征"]`）；
2. 下拉里点特征名（`.os-tool-dropdown-content`）；
3. 弹出参数对话框（`.feature-dialog`，含 Base radius/Base height/… 全部默认值）；
4. 点勾选 `.ns-dialog-button-ok.button-ok` 接受 → 特征计算。

实测最终结果：
- 特征树 `特征 (5)`，含 `Bc Branch cable trophy display 1`（isUserFeature）
- 零件列表 `零件数 (132) base plaqueInsert_blank rootCollars_0 …`
- 即「上传+编译+版本+应用+建模」全链路 0 配额闭环成功。

## 4. 实现入口

- `browser_create_document`、`browser_create_document_version`、`browser_insert_custom_feature`、
  `browser_get_page_tabs`、`browser_get_partstudio_features`、`browser_deploy_featurescript`、
  `browser_read_featurescript`、`browser_open_document`、`browser_reconnect`。
- `browser_click` 支持 `selector+text` 精确定位与 `double` 双击。

当前完整工具清单以 `docs_section(page="mcp-server")` 和 `tools/list` 为准；经验
文档只记录跨版本仍有复用价值的流程和判定信号，不复制不断变化的注册表。

## 5. 创建文档与部署细节

创建文档的稳定路径：

1. `#create-new-type` 打开 `.os-create-menu.create-new-type-menu`；
2. `button.create-new-document` 打开 `.new-document-dialog`；
3. 用 `#document-name-input` 填名，让 Playwright 触发 Angular 绑定；
4. 点击 `#model-name-dialog-ok` 或 `.new-document-dialog .btn-primary`；
5. 新文档默认包含 `Part Studio 1`、`Assembly 1` 和文档标签栏。

`browser_deploy_featurescript` 的有效信号不是“点过提交”，而是：Ace API
`setValue()` 写入全文、提交按钮从 enabled 回到 disabled、随后 `getValue()` 读回
内容完全一致并返回 `verified:true`。`dry_run=true` 只报告源码长度与行数，不启动
浏览器，也不产生页面写入。

## 6. 建模验证信号

- **部署成功**：Feature Studio 提交按钮恢复 disabled，且读回源码完全一致。
- **特征可用**：创建文档版本后，自定义特征出现在工作区特征下拉中。
- **特征已应用**：Part Studio 特征树出现 `.os-list-item.ns-user-feature`。
- **建模成功**：`.part-list-container` 的 `零件数 (N)` 满足 `N > 0`。

“添加自定义特征”选择器中的条目、Part Studio 中的 `not-computed` 行、或仅有
`feature-id` 都不足以证明建模成功。最终判定必须同时读取特征树和零件数。

## 7. 已知边界

- 部署一个已实例化 Feature Studio 的新版本后，Part Studio 通常会自动重新生成，
  无需重新插入；仍应重新读取特征状态和零件数。
- 页面和对话框受代理及 SPA 路由影响，应等待目标元素或状态变化，不能依赖固定短延迟。
- 所有真实 UI 写操作仍要求 `confirm_mutation=true`；“0 REST 配额”不等于“只读”。
- 选择器和工具注册以当前代码与离线测试为准；本文给出的是工作流语义与成功条件。

## 8. opBoolean 与命名/倒角边选择（实测 2026-08）

模块接口验证（Part A 固定壁+轨 / Part B 槽块）落地时验证的 FeatureScript 经验：

- **UNION 只传 `tools`，不要传 `targets`**：`targets` 仅 SUBTRACTION /
  SUBTRACT_COMPLEMENT / 分组模式需要。UNION 用
  `qUnion([qCreatedBy(wallExtrudeId, BODY), qCreatedBy(railExtrudeId, BODY)])`。
- **UNION 之后 `qCreatedBy(unionId, EntityType.BODY)` 为空**：UNION 保留 tools 中
  最早实体的身份，结果体仍归第一个 tool 特征所有。命名/后续查询要指向那个特征，
  否则 setProperty 抛 `无法解析图元`（CANNOT_RESOLVE_ENTITIES = 空查询）。
- **SUBTRACTION 之后同样查询 target 体**（`qCreatedBy(blockExtrudeId, BODY)`），
  不要查布尔特征 id。`qOwnedByBody(qCreatedBy(blockExtrudeId, BODY), EDGE)`
  是可靠的“结果体上的边”写法。
- **两体只共面不重叠时 UNION 会失败**：给轨道截面加一段埋入壁内的矩形嵌入段
  （Y=壁厚-0.5~壁厚），并集后嵌入段被吸收，凸出段仍保持规格截面。
- **`skPolyline` 闭多边形 + `qCreatedBy(sketchId, EntityType.FACE)` 拉伸**可靠：
  5 个互不相交的闭多边形一次拉伸得到 5 个独立 body/part。
- **倒角边方向判断要按真实几何**：槽口入口（Z=40）处的“槽口上边”是两条 45° 斜边
  （切线方向 (±0.707, ±0.707, 0)），不是沿 X 的水平边——沿 X 的边是槽底
  （Y=grooveDepth）。选边前用 `evEdgeTangentLine(edge, {"parameter":0.5})` 采样
  方向与中点坐标确认，不要凭猜测写过滤器。
- **调试技巧**：在可疑 op 前用 `isQueryEmpty` 抛 `regenError("DEBUG ...")`，或把
  `evaluateQuery` 采样到的边坐标拼进 regenError 文本，一次部署即可定位空查询来自
  哪个操作（注意错误只显示第一个失败 op，前置 op 会掩盖后续 op）。

## 9. 纵向导入斜坡（非倒角）与并集邻接（修订 2026-08）

- **UNION 只传 `tools`** 且 **邻接体（仅共面）也能合并**：壁与轨在 Y=wallThicknessY
  只共面不重叠，`opBoolean(UNION, tools=[wallBodies, railBodies])` 直接成功，
  不需要给轨加“嵌入段”（嵌入段属于未要求的额外结构，应删除）。之前失败的根因是
  `qCreatedBy(unionId)` 空 + 误传 `targets`，不是“必须重叠”。
- **1.2 mm 纵向 45° 导入斜坡**：不是端部倒角。正确构造是每条轨一个**楔形体**——
  在 Y-Z 平面画直角三角形 `(wallThicknessY, wallHeightZ) → (tipY, wallHeightZ-leadIn) → (tipY, wallHeightZ)`，
  沿 +X 拉伸根宽，再从并集体上 SUBTRACTION。斜边即“从完整轨高 1.2 逐渐过渡到端部”的 45° 斜坡。
  - 楔体 X 范围取**根宽**（不是顶宽），否则端部两侧斜边残留。
  - 楔体 Y 下界 = 壁面（wallThicknessY），不切入壁体。
- **参数显式化**：`rail_root_width` / `rail_top_width` / `rail_height` /
  `rail_pitch` / `rail_angle` 作为 precondition 显式参数 + 锁死 bounds；
  轨中心用 `first_center_x + i * pitch` 显式得到 4/12/20/28/36，禁止边缘均分。
- **验收信号**：`零件数 (1)` 且名称正确；无端部倒角特征（opChamfer 不出现于轨）。

## 10. 工程图与装配体（0 配额浏览器路径）

- 创建页签菜单项（隐藏的 `a.dropdown-item`，JS click 即可触发）：
  `创建 Feature Studio` / `创建 Part Studio` / `创建装配体` / `创建工程图…`。
- 装配体插入：装配体标签内点 `.tool.is-activatable.is-button`（title
  `插入零件和装配体 (i)`）→ 对话框 `assembly-insert-dialog` 内点选
  `.select-item-dialog-item.parent-item.os-selectable-item`（可多选）→
  点 `.ns-dialog-button-ok.button-ok`。实例树出现
  `Fixed wall (rail) <1>` / `Module block (groove) <1>`。
- 工程图标签或跨域 iframe 出现只证明容器已创建，主页面 `svg` 数量不能证明
  工程视图或尺寸已生成。`DrawingPage` 与 frame-aware 通用工具可进入
  `production-drawing-*` iframe；旧 `browser_draw_part` 现要求至少一个尺寸并验证
  每个尺寸，空列表不再因 `all([])` 误报成功。
- 实测修正（2026-08-25）：通用「创建工程图…」路径可能得到空白图纸。自动视图应
  从 Part Studio 的精确零件行右键菜单 `创建 <name> 的工程图…` 进入。
  `browser_drawing_insert_views` 选择 `four` / `single` / `iso` 语义布局，要求恰好
  一个新 drawing tab，并用 Drawing DOM 或 main-canvas PNG 墨迹分布验证视图。
  当前 Drawing DOM 没有可靠 view 节点，实际四视图的 1240×694 canvas 已经视觉确认；
  原图、SHA 和像素指标在 `dev/button-map/scan-app-shell.json` /
  `scan-drawing-four-views.png`。`browser_draw_part_with_views` 在此基础上再添加尺寸，
  任一阶段失败即 `drawn:false`。

## 11. Fixture 驱动项目与验收

- `browser_deploy_and_apply_featurescript` 把“确保 FS/PS → 提交 → 可选建版本 → 应用 →
  读取零件”固化为一个 L5 工作流，输出标准化 `{parts, partNames}`；它本身没有具体设计
  规格、最终成果验收和 manifest，因此不自动升级为 L6。
- `browser_run_project` 从 `dev/fixtures-capture/<project>.json` 串行执行，不接受任意文件
  路径；每步写本地 checkpoint。失败后 `resume=true` 只继续 pending 步骤，避免再次建文档。
  它属于 Project 控制平面而不是 L6；未来项目由一个或多个独立验收的 L6 成果组成。
  允许工具仍是闭集，但已覆盖新增 L3-L5；每个工具绑定自己的 outcome key，未知或缺失
  outcome 不再默认成功。只给实际写工具注入 `confirm_mutation=true`。
- Project schema v2 将 `setup` 与 `deliverables[]` 分开。成果节点使用
  `depends_on` 构成无环 DAG；每个节点必须有非空步骤、最终 assertions 和 outputs。
  节点验收后 checkpoint 写入 `completedDeliverables` 以及独立 manifest，其中记录
  `semanticLevel:L6`、fixture SHA、依赖、断言、media type、来源 step/key 和实际远程或
  本地成果引用。旧 v1 平面 fixture 保持兼容。
- `module-interface-deliverables` 是多 L6 fixture：两个 Part Studio 成果、一个依赖两者的
  Assembly 成果和两张分别依赖零件的 Drawing 成果。
- `module-interface-verification` 固定执行 6 步：建文档、建 rail/groove 两零件、装配、
  两张工程图；两个 drawing 步骤使用 `browser_draw_part_with_views`，最终断言零件数、
  装配状态和非空视图验收。

## 12. FDM 分析边界修正

- Onshape `拔模分析` 是制造角度可视化，不是 FDM 打印朝向分析。它不能单独证明床面
  接触、支撑、桥接、重心稳定性、打印高度、层间强度、构建体积或 Bambu Studio
  profile 下的切片结果。
- 当前 `browser_print_orientation_check` 只会得到 `assessable:false` /
  `risk:"unknown"`，六级 catalog 已将其标为 `semantically_invalid` 并默认隐藏；依赖它的
  `browser_print_optimize_part` 同样不能作为有效 FDM 工作流。
- 正确边界是：浏览器或 REST 模式各自导出规范 STEP 并构造相同 artifact contract；根级
  共享 `fdm_analysis` 库负责显式 STEP tessellation、网格指标、Bambu Studio 切片、报告
  和 manifest。共享库本身不是 MCP 语义工具。
- 一个明确朝向的模式包装器是 L4，多朝向排序/临时完整分析是 L5，包含 STEP、网格、
  3MF、报告和 manifest 的正式成果包是 L6。
