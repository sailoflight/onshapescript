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
- **工具栏下拉的行文本不是特征名**：行里先渲染 Feature Studio 的双字母徽标
  （`<div class="tool-initials-icon">Bf</div>`），再是名字
  （`<span class="tool-label">Bounded fillet</span>`），所以行的 `innerText` 是
  `"Bf\nBounded fillet"`。按整行文本与裸特征名做**精确相等**永远匹配不上（实测 2026-09-19，
  四个能力分别是 `Sr`/`Bh`/`Bf`/`Be`）。要比就比 `.tool-label` 这个**名字元素**，
  匹配失败时把下拉里实际可用的名字一起报出来。
- **用真实鼠标点击，不要用 `page.evaluate` 里的 `element.click()`**：工具栏
  「此工作区中的自定义特征」按钮用 JS `.click()` 不会展开下拉（Angular 事件不触发），
  `browser_click` 的真实点击才会。该按钮的文案在 `data-bs-original-title`，不在 `title`。
- **「创建一个版本」提示只在对话框的「当前文档」页签上**：插入对话框默认活动的可能是
  「其他文档」，那里没有提示，`browser_create_document_version` 就会报
  `no version prompt`。`browser_create_document_version` 要求对话框**已经打开**
  （`browser_open_insert_feature_dialog`，L3 默认隐藏），并且在切标签后要等对话框渲染完
  再读——`deploy_and_apply` 内部的 `create_version` 步骤读得太早，实测拿到的是
  `version prompt not present`。

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
  `browser_read_featurescript`、`browser_open_document`、`browser_session`（会话恢复走
  `action="reconnect"`）。
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

- **零件名字只能从 DOM 取；归一化后的 `partsText` 不足以切名字（2026-09-20 实测，已修）**。
  `read_partstudio_features` 把 `.part-list-container` 的文本按 `\s+ → 单空格` 归一化
  并截断到 400 字符，而 `parse_part_summary` 按 `\s{2,}|\n` 切名字 —— 归一化之后这个
  切分永远不会命中，于是两条分支都错：`count == 1` 走特例，把整个剩余串当成一个名字
  （实测 `零件数 (1) 螺旋凸棱柱 曲线数 (1)` → `["螺旋凸棱柱 曲线数 (1)"]`，把下一个分区
  表头 `曲线数` 吞进了名字）；`count > 1` 直接返回 `[]` 且 `partNamesParsed: false`
  （实测 `零件数 (9)` 与 `零件数 (11)` 两次）。
  修法：`read_partstudio_features` 现在同时返回 `partItems`（按 `.os-list-item` 的
  `os-part-list-icon` 认零件行），`parse_part_summary(parts_text, part_items)` 在
  `len(partItems) == parts` 时用 DOM 名字并标 `partNamesSource: "dom"`；文本兜底只在
  计数自洽时用，并新增拒绝：`count == 1` 的剩余串里若还含 `…数 (N)` 分区表头，就
  不再编造名字（宁可 `partNames: []` + `partNamesSource: "none"`）。判定建模成功只看
  `parts > 0`；要写名字必须核 `partNamesSource == "dom"`。

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
  `browser_draw_part_with_views` 的视图阶段选择 `four` / `single` / `iso` 语义布局，
  要求恰好一个新 drawing tab，并用 Drawing DOM 或 main-canvas PNG 墨迹分布验证视图。
  当前 Drawing DOM 没有可靠 view 节点，实际四视图的 1240×694 canvas 已经视觉确认；
  原图、SHA 和像素指标在 `dev/button-map/scan-app-shell.json` /
  `scan-drawing-four-views.png`。同一个工具再按 `dimensions` 添加尺寸，只要给了
  `part_name` 和 `dimensions` 就两阶段都要求通过，任一阶段失败即 `drawn:false`；
  只给 `dimensions` 则只做尺寸阶段，只给 `part_name` 则只做视图阶段（视图-only
  返回的就是旧 `browser_drawing_insert_views` 的 `viewsInserted` 证据）。

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
- `browser_print_orientation_check` 只会得到 `assessable:false` /
  `risk:"unknown"`，六级 catalog 曾将其标为 `semantically_invalid` 并默认隐藏；依赖它的
  `browser_print_optimize_part` 同样不能作为有效 FDM 工作流。这两个名字已于 2026-09-19
  归档并从工具表移除（源码留档：`../../docs/history/legacy/ARCHIVED_BROWSER_PRINT_TOOLS.md`）。
  **可复用教训**：一个永远做不到名字所承诺工作的工具，比没有这个工具更糟 —— 失败闭环
  只能证明"没做"，不能证明"不能做"；这类名字应当归档，而不是长期 fail-closed 占位。
- 正确边界是：浏览器或 REST 模式各自导出规范 STEP 并构造相同 artifact contract；根级
  共享 `fdm_analysis` 库负责显式 STEP tessellation、网格指标、Bambu Studio 切片、报告
  和 manifest。共享库本身不是 MCP 语义工具。
- 一个明确朝向的模式包装器是 L4，多朝向排序/临时完整分析是 L5，包含 STEP、网格、
  3MF、报告和 manifest 的正式成果包是 L6。

## 13. 能力契约（whole-feature capability contract）

`browser_spiral_ridge` 的形状被抽成契约，实现是
`onshape_browser_mode/capabilities.py`：能力 = 数据 + 源码生成器，不是又一个工具实现。

**契约**

- 调用方只给 **有界值**：`length`（mm，带 min/max）、`number`、`boolean`、封闭
  `enum`。没有自由字符串、没有代码、没有 selector。
- **Query 不是能力参数**：选面/选边留在生成特征的 `precondition` 里，由人在
  Onshape 对话框里、看得见几何的情况下选。所以能力无法被要求去倒一个不存在的边。
  **实测代价**（2026-09-19）：必填 `Query` 未拾取时 Onshape 会禁用接受键，所以一个
  只会给标量值的调用者能部署、能编译、能列出来，但**无法完成**这类能力——它们目前
  是人类在环的能力，不是代理端能力。只有自己从数字生成几何的能力
  （`custom.spiral_ridge`）能端到端自动跑通。原生特征那条路已有语义目标选择通道
  （`browser_apply_blend` 的 semantic targets），能力层要真正可被代理调用，需要等价物
  或者自带几何。
- **能力数量与工具数量解耦**：新增能力不新增工具。当前四个能力
  （`custom.spiral_ridge` / `custom.fillet` / `custom.extrude` / `custom.hole`）都通过既有的
  `browser_deploy_and_apply_featurescript` 调用，schema 用
  `anyOf: [script+feature_name, capability]` 表达两条互斥路线，handler 再做一次校验。
- 卡片（`capabilities.cards()`）只含身份、`useWhen`、参数与验证状态，**不含实现**；
  实现只在 dry-run 预览里为人工审阅而出现。

**怎么找到能力（发现路线）**

`browser_discover_tools(query=...)` 在返回工具候选的同时，会把匹配的**能力卡片**
附在 `capabilities` 字段里（同一个工具，没有新增工具，也没有放宽 L1/L3 的默认暴露）。
每张卡还带 `invocation`：能力不是注册工具名，而是作为
`browser_deploy_and_apply_featurescript` 的 `capability` + `values` 参数，
所以卡自己给出准确的调用（`values` 是卡片默认值，只做起点）。工具候选则相反：
按 `browser_discover_tools` / `mcp_tool_catalog` 返回的精确注册名直接调用。
`capabilities.search(query, limit)` 最多返回 5 张卡，排序为
身份（id / 别名）→ 特征类型 → `use_when` 散文；单个偶然的散文词（"feature"、
"part"）不足以命中，只有一个弱词也不算匹配。

同一条能力卡片也出现在 `mcp_tool_catalog` 的搜索结果里（`capabilities` 字段），
因为那才是文档认可的 lookup-first 入口：查 "hole" 时工具结果为 0（没有这个工具），
但卡片给出 `custom.hole` 与可执行的部署调用。顺带修掉一个路由错误：tokenizer 读不出
非空查询（例如中文）时，以前会「匹配全部 108 个工具」——那不是宽搜索，而是路由失败；
现在返回 0 个工具摘要，卡片仍然能解析。

`dev/tests/test_capability_retrieval.py` 是这条路的门：
- 卡片路线的载荷是 668–1422 字符；同一条查询走参考索引要 1862–8930 字符，而且**还没
  读完**定义契约的那个函数体。
- "round the edges of this part" 这种意图式查询能解析到 `custom.fillet`，而
  FeatureScript 搜索只会排出一堆 query helper / filter —— 卡片层的价值不只是省字符。
- 卡片载荷里没有任何源码；解析一张卡不会触碰 `get_function` / `library_source` /
  `guide_section`（测试用 mock 断言这三者零调用）。
- 这是**字符**测量，不是带模型 loop 的 token 测量；"调用方读完卡片就停"没有被证明，
  只证明了离线路线不需要实现源码。

**每个模板只用 vendored 参考里确实存在的符号**

`dev/tests/test_capabilities.py` 会从生成的 FeatureScript 里抽出所有调用名、
`Enum.Member` 与全大写常量，逐个对照 `onshape_docs/reference/`（索引 + 枚举成员）。
这不是「我觉得对」，而是「参考里确实有」；调用名或枚举成员写错会直接失败。
`opFillet` 的 `entities`/`radius`/`tangentPropagation`、
`opExtrude` 的 `entities`/`direction`/`endBound`/`endDepth`、
`opBoolean` 的 `tools`/`targets`/`operationType`，以及 `BLEND_BOUNDS` /
`LENGTH_BOUNDS` 常量，都取自 vendored 标准库源码（`geomOperations.fs`、
`valueBounds.fs`），而不是模型记忆。

**孔（`custom.hole`）：一次基于证据的推翻。** 早期结论是「不加 `custom.hole`，
因为 `holeDefinition` 的构造无法离线确认」。查过 vendored 源码后这个理由不成立：
`opHole` 的字段（`holeDefinition` / `axes` / `targets`）与示例写在
`geomOperations.fs`，`holeDefinition(profiles)` 单参重载、`holeProfile(
positionReference, position, radius)` 构造器、以及「最后一个 profile 的半径必须是
0」的规则写在 `holeUtils.fs`，`AXIS_POINT` / `LAST_TARGET_END` 是
`holepositionreference.gen.fs` 里的枚举成员，`line(origin, direction)` 来自
`curveGeometry.fs`，`evVertexPoint` / `evPlane` 来自 `evaluate.fs`。所以孔的形状是
**可被符号门检查的构造调用**，不是猜出来的 map 字面量。轴由人的两次选择决定
（起点顶点 + 平面面，钻孔方向取面法线的反向），通孔用 `LAST_TARGET_END` 引用而不是
一个很大的深度值。状态仍是 `structural-only`。

**验证状态要说清楚**（实测记录：
[`verification/capability-live-run-2026-09-19.md`](../verification/capability-live-run-2026-09-19.md)）

- `custom.spiral_ridge` — `live-verified`：源码与被应用的特征都经真机验证过，且
  `test_capabilities` 断言它渲染出的源码与 `generate_spiral_ridge_script` 结构逐字相同
  （只用本卡默认值时两者仅参数值不同），证明「抽契约」没有走样。真机结果：特征树
  `Sr Spiral ridge 1`（`hasError: false`）、`零件数 (1)`、零件 `Spiral ridge cylinder`。
- `custom.fillet` / `custom.extrude` / `custom.hole` — **已服务端编译，未产生几何**。四份源码
  都在真实服务器（FeatureScript 3044）上 `compiled: true`、0 error、0 warning、0 notice，
  且部署前后的源码逐字节核对过（只差结尾换行）。**但这三个没有应用成功、没有产生过几何**：
  它们的必填 `Query` 没被拾取时 Onshape 直接把接受键置灰（`button-ok disabled`），
  代理端无法完成。任何几何结论都不得从这里推断。
- 因此这三条的真机验证只补齐了 P2 gate 的 deploy 半场；apply/几何半场对选择型能力仍然
  打不开，原因见下。

**加一个能力的顺序**：在 `CAPABILITIES` 里加一条（id、`feature_type`、别名、
`use_when`、参数、`build_source`）→ 让 `test_capabilities` 的符号门与本地检查器通过
→ 真机跑 dry-run → deploy → apply → 用 `featurePresent`/`featureComputed`/零件数三项
验收。别名冲突会在 `resolve()` 里直接报错，不会变成模糊路由。

## 14. 真机验证前先核对「跑的是哪份代码」

**实测（2026-09-19）**：`browser_deploy_and_apply_featurescript(capability=..., dry_run=true)`
返回 `ValueError: script and feature_name are required`——而这句话在本仓库里根本不存在。
原因是运行中的 Onshape MCP 服务是 Windows 上的普通 stdio **部署副本**
`C:\MCP\onshapescript`（一份拷贝，不是 checkout），它落后于仓库：`capabilities.py`
不存在、`semantic.py` 没有未计算特征守卫、注册工具数 106（当时仓库 108）。

> 注意：`106` 当时是**落后**的标志；2026-09-19 归档两个 print 工具后仓库自身也是 106，
> 于是两边数字相等而内容不同 —— 实测同日的对照是：部署副本 `browser`=68 /
> `featurescript`=10 / `rest`=17，仓库 `browser`=66 / `featurescript`=11 / `rest`=18。
> 因此**只比数字会漏判**，必须比指纹：`mcp_tool_catalog(action="status").fingerprint`
> 当时是 `754218124c1b28c4…`，仓库 `ToolCatalogIndex(FINGERPRINT 源)`
> 算出 `272cc39d6f0fa4b3…`；不等即说明线上不是当前代码。

后果很实际：**仓库是绿的、测试是过的、能力层是从未在线上跑过的。** 所以：

- 真机验证前先读 `mcp_tool_catalog(action="status")`，把 `fingerprint` 与仓库算出的
  `ToolCatalogIndex(server.TOOLS).fingerprint` 比对；不等就说明线上不是当前代码。
  `registryCount` 只用来解释差异（多了什么、少了什么），不能单独当判据。
  上段两个指纹值是 2026-09-19 的**测量记录**，不是常量：仓库侧任何 description /
  schema 改动都会改变它（同日的八项工具合并就把仓库侧指纹换成了新值）。要比的是
  「当场读到的线上值 vs 当场算出的仓库值」。
- **再加一条独立的逐文件哈希佐证（2026-09-20 实测）**。对仓库与部署副本各遍历一遍
  白名单后缀（`.py/.md/.json/.fs/...`）、跳过 `.git`/`.venv`/`outputs`/`temp` 等目录，
  逐文件比对 sha256：当日仓库 651 文件 vs 部署 556 文件，**所有随代码发布的文件
  逐字节相同**，仅 3 个不同且都可解释 ——
  `onshape_browser_mode/config/geometry-backend.json`、
  `onshape_rest_api_mode/config/onshape-state.json`（宿主运行期状态）与
  `.agent-project-guides.json`（治理文件，不随代码发布）。指纹相等是必要条件，
  哈希相等把结论从"某个数字相等"升级成"内容相同"，也是判断**是否需要**刷新部署
  最省事的依据（当时结论：不需要，因此省掉一次会关掉浏览器会话的重启）。
- **指纹只在"工具表面"变了才动；改模块**行为**它不会动（2026-09-20 实测）**。修好三个
  浏览器缺陷（枚举口径、标签删除判据、DOM 零件名）后重新部署，`mcp_tool_catalog
  (action="status").fingerprint` **改前改后完全一致**（`7091559f…`），而且与仓库算出的
  值也一致——因为它只由工具名/schema 决定，这次一行 schema 都没动。也就是说：
  指纹相等**不能**证明线上代码是当前代码，这一类改动的唯一门是逐文件哈希
  （`deploy.py plan/verify`：当日 589 个仓库源文件、11 个 changed、0 missing、
  578 identical；刷完后 `shippedPresent: 589`、`mismatched: []`）。先跑只读 `plan`
  看漂移，再 `apply`（自动写前像到 `artifacts/deploy-backups/<id>`），最后 `verify`。
- **文件拷完还要换进程才算上线**。部署是**文件拷贝**而非 checkout，Python 只在首次
  import 时缓存模块，所以"拷完即生效"不成立：必须让宿主重开该 stdio 后端。当日用
  `bridge_control(action="restart", id="onshape", expectedGeneration=3)` 完成，返回
  `ownedGeneration: 3 → 4`、`preservedClients: 1`、`reconnectRequired: false`、
  `force-kill/not-needed`；注意 `bridge_control(action="refresh")` **只**广播
  `notifications/tools/list_changed`，**不会**重启后端、也不会加载新代码。代价是该进程
  持有的浏览器一起结束、Onshape Web 会话登出，需要一次人工登录。**注意"profile 持久所以
  很便宜"是错的**（2026-09-20 实测更正）：profile 持久**不能**保住登录态，见下条。
- **Onshape 没有"保持登录"：浏览器进程一关就登出，profile 持久救不了它（2026-09-20 实测）**。
  - 实测两种死法**都登出**：`browser_session(action="release")`（`releaseMethod:
    "context.close"`，与桥重启执行的是同一次关闭）之后**不登录**打开文档 →
    `opened: false` + `pageUrl: .../signin`；改成 `Stop-Process -Force` 强杀该 profile 的
    8 个 Edge 进程（浏览器侧没走干净退出）后同样 `opened: false` + `/signin`。所以登出
    **不由关闭方式决定**，强杀/残留也救不回来。
  - 底层原因（实测 cookie 库）：`.onshape.com on-session-id` 与 `cad.onshape.com _u` 都是
    `persistent=0 has_expires=0 secure=1 httponly=1`，是**会话级 cookie**，只活在浏览器进程
    内存里；磁盘上持久的只有 `_ga*` 与 `aws-waf-token`。取证注意：读库必须在浏览器关闭后做
    —— 运行中 Chromium 独占该文件，WSL 直接读和 Windows 侧 `Copy-Item` 都会被拒；而且刚访问过
    `/signin` 时的 `on-session-id` 可能是**匿名**会话，只有 cookie 的**类型**是可靠证据。
  - 所以"要不要重新登录"只取决于**浏览器进程有没有活着**。仓库 2026-08-20 的
    `tools/windows/README.md`（commit `e149bdf`）早已写明：*"Onshape WEB 端没有'保持登录'，
    浏览器一关立即登出"*，并给出正解 —— 浏览器由**常驻进程**持有、客户端断开只关 socket，
    只有常驻进程退出才关浏览器。
  - 当前架构丢掉了这个性质：`win-wsl-mcp-bridge` **每个连接拉起一个新的 MCP 子进程**，
    而 `mcp_main/win/mcp/server.py` 在 stdin EOF 时 `session.close()` 释放 profile（该行为由
    `9394ad0` 引入，为的是避免下一次启动撞 "profile is in use"），于是**任何断开/重启都要
    人工登录一次**。要恢复旧性质必须让浏览器活过子进程、后续子进程用 CDP 附着
    （`browser_common` 没有 attach 能力；本仓库 `playwright_factory` 注入点是实现入口）。
    本仓库已按此实现，见 §16。
  - 判定注意：重启后 `browser_session(action="login")` 报 `awaiting_login` /
    `humanActionRequired: true` 是**正确**的（不是误报），但它会**无条件**把状态置成
    awaiting_login，所以"它说要登录"与"登录真的丢了"是两件事；要判定登录是否还在，用一次
    只读导航（如 `browser_open_document`）而不是这个状态字段。

- 同日的合并还改变了普通 `tools/list`：八个被吸收的兼容名不再出现在普通视图（浏览器
  名通过 `default_exposure=False`，`fs_list_modules` 通过 `ABSORBED_COMPATIBILITY_TOOLS`），
  所以普通列表从 80 降到 72，而注册表仍是 106。数字下降**不等于**工具变少。
- 再用**只在仓库里存在**的一个能力参数（例如 `capability=`）探一下该工具的真实 schema。
- 结论要按事实写：「验证的是生成出来的源码与浏览器应用链路」，不要写成「能力层已验证」。
- 部署副本里 `browser-state.json` / `browser.local.toml` 是 Deployment 本地状态，
  刷新部署时必须保留。
- 刷新部署是**部署动作**（要重启服务端，会关掉浏览器进程），不属于开发/验证范围，
  需要单独授权；浏览器登录态在持久 profile 里，但仍应事先说明。

## 15. 选择型能力的真机边界

必填 `Query` 未拾取时，Onshape 特征对话框的接受键是禁用的：

```
.ns-dialog-button-ok.button-ok  ->  class "… disabled", attribute disabled
```

按钮存在、可见、可点，但点它不会接受特征。所以「部署成功」与「能力可用」是两件事：
`custom.fillet` / `custom.extrude` / `custom.hole` 的真机结论停在 **服务端编译通过**，
`built` 类字段不能被当成几何证据。验收这些能力需要先有一条把几何选择也表达出来的通道。

一个附带发现：自定义特征在 UI 上确实与官方特征等价。打开 `Bounded fillet` 得到真正的
`.ns-dialog-panel.feature-dialog`（标题 `Bounded fillet 1`），字段就是 `precondition`
里按顺序写的注解 `["Edges to fillet", "Radius", "Tangent propagation"]`，特征树里出现
待接受的 `Bf Bounded fillet 1` 行。取消后特征树回到 `特征 (5)`，没有残留行。

## 16. 常驻浏览器：让登录活过 MCP 子进程

目标是把"每次桥重启都要人工登录一次"（§15 前那条的结论）消掉，手段是让浏览器由
**自己拉起的独立进程**持有，后续每个 MCP 子进程只**附着**不托管。

关键实测（2026-09-20，真机 Windows，`artifacts/cdp_close_probe.py`，临时 profile + 端口 9334，
不碰 Onshape profile，0 Onshape REST 配额）：自己 `Popen`（`DETACHED_PROCESS |
CREATE_NEW_PROCESS_GROUP`）拉起 Edge 并带 `--remote-debugging-port`，然后
`connect_over_cdp()` 附着，再调用 `browser_common` 释放资源时用的那一次
`context.close()`：

```
STEP1 endpoint=up            targets=[about:blank, chrome-extension://…(6 个后台页)]
STEP2 connected contexts=1 connected=True  pages=1 urls=['about:blank']
STEP3 context.close() returned
STEP3 endpointAfterClose=up                 targetsAfterClose=[同前，一个都没少]
STEP3 isConnectedAfterClose=False           contextsAfterClose=0
STEP4 secondAttach contexts=1 pages=[1]     urls=['about:blank']
STEP5 endpointAfterStop=up                  targetsAfterStop=[同前]
```

读法：`context.close()` **不断开**浏览器进程、**不关**标签页，它只是**分离**了这次
Playwright 连接（`isConnected` 转 False、`contexts` 归零）；第二次附着又能拿到 1 个
context + 1 个页面，`playwright.stop()` 同样不影响端点。原因是 **Chromium 无法销毁浏览器的
默认 context**，所以对这个连接而言 `close()` 等价于 detach。

这条测量直接决定了适配层的形状，而且是"少写代码"的方向：

- **不要**用代理上下文包装真实 context。最初的设计写了一个 `close()` 空实现的外壳，理由是
  "关了就会杀掉常驻浏览器"；实测证伪后它只剩坏处：`browser_common` 在 `reconcile_pages` /
  `temporary_pages` 里会断言 `page.context is session.context`（`_core._validate_pages`），
  外壳会让这条断言全部失败，而 `_enforce_single_working_page` 在每次页面交接时都走它。
  直接返回**真实** context，身份断言自然成立。
- **也不要**依赖 `close()` 抛异常：`sync_session._release_resources` 在 `context.close()`
  抛错且 `browser_close_fallback=True` 时会**回退**去调 `context.browser.close()`，
  那才会真的关掉常驻浏览器。正常返回的 `close()` 会把 `_context_closed` 置真、跳过回退，
  这正是我们要的路径；`browser_close_fallback` 保持默认即可。
- **必须自己 spawn**，不能 `launch_persistent_context()`。Playwright 托管的浏览器在
  `context.close()` / `playwright.stop()` 时会一起结束（早前实测：`context.close()` 后端点
  消失），所以"交给 Playwright 启动"与"活过子进程"不能同时成立。
- 端点参数：`--remote-allow-origins=*` 必须加上（Chromium 111+ 拒绝带 `Origin` 头的
  DevTools websocket）；端点默认只绑回环，**绝不能**转发到回环之外——它等于登录态的完全控制权。
- `viewport` 在附着模式下无法按 context 设置（不能去改不属于本进程的页面），只能映射成
  spawn 时的 `--window-size`；`headless` / `timezone_id` 没有对应物。这些**不静默忽略**，
  而是在 attach 记录里作为 `notApplied` 报出来。

离线可验证的部分（`dev/tests/test_browser_resident.py`，25 项）：端点已有 → 只附着不 spawn；
端点没有 → 恰好 spawn 一次且 argv 精确；端点始终不出现 → 干净失败并说明"可能被别的无端口
浏览器占了 profile"；无默认 context → 拒绝新建（新 context 不带登录）；并且用**真实
`browser_common.SyncSession`** 跑一遍 release，断言 `context.close` 恰好一次、
`browser.close` 零次、`report.clean`。

真机认证（2026-09-20，桥代数 10→11→12，0 Onshape REST 配额；详情见
`verification/capability-live-run-2026-09-19.md` 第六步）：**不登录**重启桥后
`/json/version` 的 GUID、`user-data-dir` 主进程 PID 3872 与其创建时间、`/json/list`
里的页面目标全部**一字不变**，profile 进程数从 14 降到 9（空闲渲染/工具进程退出，
浏览器本体没退），新 MCP 子进程能读到那个活着的页面；人工登录一次后，再次重启
（11→12）后 `browser_get_page_tabs` 与 `browser_session(status)` 都直接给出目标文档
`.../e/b1d0caa1e06f62da338d0ef8` 的 10 个标签页，`loginConfirmed: true`、
`humanActionRequired: false`，全程没有登录也没有导航。**"重启要重新登录"这个五年来的
既定代价到此消失**（首次运行与真正关掉浏览器窗口仍需一次登录）。

这一轮真机还踩到两个只在真实环境出现、离线测试不会报的坑，值得记住：

- **通用启动错误消息会把根因吞掉**。`browser_open_document` 只回
  `Could not launch browser (channel='msedge'): TypeError.`——类型名给了线索，但没有回溯。
  正确做法是在**部署侧**用一个小脚本直接复现同一条路径（`artifacts/resident_debug.py`：
  `BrowserSession(cfg)._make_resources().start()` + `traceback.print_exc()`），一次就定位到
  `ResidentChromium.__init__() got an unexpected keyword argument 'viewport'`：`_make_resources`
  把 `viewport` 这个**逐页 launch 选项**又当生成参数传了一遍，而它本来就会经
  `SessionConfig.launch_kwargs()` 到达 `launch_persistent_context`。教训：接线错误要让
  **构造函数保持严格**（多传未知 kwargs 立刻 TypeError），并且在离线测试里补一条
  "适配器必须能接受开关实际发的那组参数"。
- **这台 Windows 有系统级 HTTP 代理，`urlopen` 默认走它**。`urllib.request.getproxies()`
  返回 `http://127.0.0.1:10808`（v2rayN 写的注册表项），于是探测 `127.0.0.1:9333` 时
  "没有浏览器"和"探测本身坏了"变得无法区分。而且本机连**关闭**的回环端口要 **~2.03 秒**
  才给 `ConnectionRefusedError`（9333/9334/9399 都是 2.03 s），原来的 2.0 s 超时正好把
  "干净拒绝"变成"超时"。修法是 `ProxyHandler({})`——注意空 ProxyHandler **不会注册任何
  `*_open` 方法**，所以它在 handler 链里等于不存在，断言要断"链上没有 ProxyHandler"而不是
  "ProxyHandler 的 proxies 为空"；超时预算同时提到 3.0 s。凡是探测**回环**端点的代码都要
  显式绕开系统代理。
- **状态字段的成功分支也要独立复核**。人工登录后 `browser_session(action="login")` 回的是
  "already logged in (restored Onshape page was kept)"，走的是第 445 行那个"当前页已是
  应用 URL"的分支——它只反映**这一瞬间**的 `page.url`。本轮用 `browser_get_page_tabs`
  独立读标签页确认了它是对的，但结论应建立在标签页/文档 URL 这类**事实读**上，而不是
  建立在状态字符串上（上一轮已记录：`awaiting_login` 是无条件置位的）。

## 17. 几何包质心是最便宜的不对称检测器（实测 2026-09-20）

Gridfinity 2x2 底板（84 x 84 x 10，4 个型腔 + 16 个磁铁孔）出现过这样一个状态：
特征树三行全部 `hasError: false`、几何包 `watertight: true`、尺寸正好 `[84, 84, 10]`
——**但模型仍然是错的**。

- 未切割的板体几何包质心 `[-0.0, 0.0, 5.0]`（精确对称），说明分析器本身没有系统偏差；
- 加上型腔与孔之后，质心变成 `[-0.205846211, -0.205846626, 3.506100101]`：x/y 同时
  偏移约 0.206 mm。对称件不该偏，于是可以断定有特征摆错，而不是"看起来差不多"。
- 根因：磁铁孔沿用了"格心"含义的 `firstCell` 变量，却套了"格角"公式
  `firstCell + {d, pitch - d}`，得到 x ∈ {-13, 13, 29, 55}（55 已在 84 mm 板外，16 个孔
  里 7 个落空）；参考实现给的是 `firstCell ± (pitch/2 - d)` = {-34, -8, 8, 34}。
- 修正后质心 `[0.000114, 0.0000113, 3.499408]`；体积 36628.55 → 36011.47 mm³
  （−617 mm³，正好等于那 7 个原本落空的孔该挖掉的料），三角面 30940 → 39456。

教训：`browser_build_geometry_package`（离线、0 额度）给出的 `centerOfMassMm` /
`volumeMm3` / `triangleCount` 是**免费**的几何断言。`hasError: false` 只证明"能算出来"，
不证明"放对了"。对称零件的正确用法是：先量一次基准件质心，切完再量一次；质心偏移超过
tessellation 量级（这里 0.206 mm 远大于 1e-4）就说明有摆放错误，体积差还能反过来
核对"少挖了多少料"。

## 18. 已建好的文档里更新 FeatureScript：只提交、不加行（实测 2026-09-20）

改完 `.fs` 不必重建文档：**Feature Studio 的提交会让工作区里已插入的自定义特征行重新
计算**。`dev/fixtures-capture/gridfinity-refresh-fs.json` 把这一步固化成单步项目
（`browser_deploy_and_apply_featurescript` + `apply: false`）：它从磁盘读 `script_file`，
所以提交的字节就是打包好的字节，返回值里的 `diagnosticCapture.sourceSha256` /
`sourceLength` 可以直接和 `sha256sum` 对账，而且**不新建文档、不新增特征行**。

- 项目运行器会把这步报成失败（`TOOL_OUTCOME_KEYS` 要求 `built`，而 `apply: false`
  什么都不 build），但同一份结果里 `deployed` / `verified` / `commitAccepted` 都是真值。
  验收要用别的读：`browser_get_fs_compile_status`（`documentClean`）、
  `browser_get_partstudio_features`（行与 `hasError`）、再重新导出 STEP + 几何包。
- 提交那一刻读到的 Part Studio 通知可能还没刷新；重算结果要在下一次读取里看，本次读到的是
  Part Studio 容器里的 `Result: Regeneration complete`。
- 实测对账：编辑器内容 23760 → 24534 字节，`sourceSha256` = `40d1064b…`，
  与仓库 `sha256sum dev/fixtures-capture/gridfinity-baseplate.fs` 一致。

## 19. 参考几何要读成「膨胀」而不是「同心堆」（实测 2026-09-20）

Gridfinity 底板的两处几何错误都来自**读错参考实现**，而且都能从导出的 STL 里用量到
0.01 mm 的证据反推出来（原始证据见 `onshape_docs/verification/gridfinity-profile-2026-09-20.md`）。

**参考实现在做什么**（`kennetek/gridfinity-rebuilt-openscad`）：

- `_BASEPLATE_PROFILE = [[0,0],[0.7,0.7],[0.7,2.5],[2.85,4.65]]`，
  `BASEPLATE_INNER_RADIUS = 4 - 2.85 = 1.15`；
- profile 平移 `(INNER_RADIUS, clearance = height - 4.65 = 0.35)` 得
  `(1.15, 0.35) -> (1.85, 1.05) -> (1.85, 2.85) -> (4.00, 5.00)`；
- `baseplate_cutter` 用 `sweep_rounded(size - BASEPLATE_OUTER_DIAMETER)`，即**沿一个
  直角 34 x 34 方框扫掠**，所以 z 处的型腔截面 = 该方框按偏移 o(z) 的 Minkowski 膨胀：
  **半宽 = 17 + o(z)，圆角半径 = o(z)**（不是 `o + 常数`）。

两处真正做错过的点：

1. **圆角半径就是 o 本身。** 旧写法把角柱放在 `wireHalf - wireRadius`、半径取
   `wireRadius + o`，顶部圆角半径于是 1.15 + 4.00 = 5.15 mm，比板块自己的 4 mm 圆角还大
   1.15 mm → 型腔在四角切穿外缘。正确值顶部 4.00 mm，与外格方框角（38, 38）处的板块
   圆角**同圆心**，所以最外圈是刀刃而不是缺口。
2. **平边必须随 z 一起涨。** 膨胀 = 方框本身 + 四边各一条宽 o 的条 + 四个半径 o 的角圆。
   旧写法只有角在长大，平边在全 z 上始终相距 34 mm，45° 只在角上"鼓包"。切片证据：
   z = 5.70 处平边半宽实测 17.80 mm，规格 18.50 mm，正好差 0.35 mm = 面往内倒了 0.35 mm。

**45° 斜条怎么建（仍然 0 草图）**：常数段用 `fCuboid`；45° 段用 `fCuboid` + `opDraft`
（中性面取该段底面）。不要用带拔模的拉伸：矩形拉伸会在**另一个轴**也涨出去，吃掉角柱。
选面用 `qParallelPlanes(qCreatedBy(id, EntityType.FACE), vector(1, 0, 0), true)`，
正好得到 ±x 两个面。

**`opDraft` 的方向约定（实测）**：拔模面的法线朝 **pull 向量**旋转。中性面在下、
`pullVec = +z` 时柱条随 z **收窄**（就是上面 17.80 的证据）；要让它随 z 张开，必须
`pullVec = vector(0, 0, -1)`。

**自检要针对真正承担该几何的 body**：对整个切刀求 `evBox3d` 抓不住方向错误——角锥自己就
能达到顶部宽度，切刀外框依旧"正确"。改成对每条斜条单独 `evBox3d`，断言它在拔模轴上达到
`wireHalf + o`、另一轴仍是 `wireHalf`，方向错就抛 `regenError`：0 额度，提交后读 Part Studio
通知即可判定。

**验收：切片探针比高度图更直接**（`temp/gridfinity_slice_check.py`）。取几何包里的二进制
STL，在若干 z 平面求截面，自格心沿 +x 求最近交点 = 平边半宽，沿 45° 对角线求最近交点 =
`17*sqrt(2) + o`。`gridfinity-2x2-final-4`（29300 面）实测全部命中：

| z | o(z) | 平边半宽 实测/规格 | 圆角半径 实测/规格 |
|---|---|---|---|
| 5.20 | 1.15 | 18.15 / 18.15 | 1.15 / 1.15 |
| 5.70 | 1.50 | 18.50 / 18.50 | 1.50 / 1.50 |
| 6.50 / 7.50 | 1.85 | 18.85 / 18.85 | 1.85 / 1.85 |
| 8.50 | 2.50 | 19.50 / 19.50 | 2.50 / 2.50 |
| 9.50 | 3.50 | 20.50 / 20.50 | 3.50 / 3.50 |
| 9.95 | 3.95 | 20.95 / 20.95 | 3.95 / 3.95 |

顶部开口 21.00 mm = 半格（相邻插座刀刃相接），顶部圆角 4.00 mm = 板块 R4。磁铁孔同样可测：
z = 4.90 交点 +3.95 mm（倒角段 3.25 + 0.7）、z = 3.00 交点 +3.25 mm（半径）、z = 2.55 起
无孔（深 2.4）。

**免费的整体断言**：`bedContactAreaMm2` = 7042.2495 mm²，而 84 x 84 圆角矩形（R4）的解析
面积 = 7056 - (4 - pi) * 16 = 7042.27 mm²——底面面积本身就证明板体形状对了（改之前
5926.75，正好少掉四条边长 76/84 的边条）；0.02 mm² 的差是网格化量级。

**没有浏览器/GUI 也能看图**：`temp/stl_render.py` 是纯标准库的软件光栅器（正交轴测 + 背面
剔除 + z-buffer + 平面着色），把几何包里的 STL 直接渲成 PNG，改前/改后各出一张即可肉眼对账。

## 20. 项目 runner 会死在 relay 超时上：中途孤儿行与「逐行直接调用」兜底（实测 2026-09-21）

`browser_run_project` 的每一步都返回完整特征树，而单次 MCP 调用受传输上限约束
（本环境实测约 60 s）。23 步的 Gridfinity 变量化重建跑到第 4 步左右，整个调用以
`downstream_timeout` 结束，随后 2.5 分钟没有推进——**最后一步的行已经建好，但没有写进
checkpoint**（孤儿行）。五个必须知道的边界：

- 恢复必须 `resume=true`；存活的 checkpoint 会让一次全新 run 直接
  `ValueError: Checkpoint already exists`；
- checkpoint 把夹具指纹绑定为**夹具 JSON 的 sha256**，所以**改夹具的任何一个字节**
  （哪怕只是参数）都会作废检查点，resume 拒绝：
  `ValueError: "Project fixture changed after checkpoint creation; start a new run"`；
- **每个步骤都必须返回一个真值 outcome key**（`TOOL_OUTCOME_KEYS`，v1/v2 两版 schema
  都要求）：`browser_insert_custom_feature` 的键是 `inserted`。短路径
  （`verify_commit: false`）故意返回 `inserted: null`，所以**它永远过不了 runner 的完成门**
  ——这样的步骤只能放到 fixture 之外跑，或改用完整校验路径；
- `MCP error -32001: downstream_timeout` 是**客户端放弃**而服务端调用仍在继续，所以行可能
  在超时报错**之后**才落地：这个报错说的是「不知道」，不是「写失败」；
- 于是「重跑一遍」不是幂等的：孤儿行会留在树里，被下一次同名等待或提交计数当成既有行。

结论：**步骤多、每步都贵的构建，逐行直接调 `browser_insert_custom_feature`**（每行
10-20 s，稳定低于传输上限），runner 留给步骤少或单步轻的项目。孤儿行要么补记到证据里，
要么在重试前删除。

**补充（实测 2026-09-21，8 步 / 4 个自定义特征的 4U 盒子）**：checkpoint 静止 ≠ 恢复安全。
那次 `downstream_timeout` 之后 checkpoint 的 `updatedAt` 静止了两分多钟，但它只记到
`04-outer-sketch`，而真实树里**第 5 步的行已经在了**（`TE Thin Extrude 1` + `Part 1`）。
只按 checkpoint 判断就会重跑第 5 步，多出一个实体。恢复前的对齐动作是两条：

1. 读真实树（`browser_get_partstudio_features`，表头计数 + 行名）与 checkpoint 的
   `completed` 对照，找出「已落地但未入账」的行；
2. 用受支持的工具删掉这些行（`browser_delete_feature`，判据是行离开列表），再
   `resume=true`。

按这个顺序做完，8 步一次跑完，每步都是 `inserted: true`（见
`onshape_docs/verification/4u-box-2026-09-21.md`）。

## 21. 四个会误判的工具行为（实测 2026-09-21）

- **`browser_create_tab` 可能对新标签报 `created: false`，但它其实已经建好了**（新标签
  还没渲染出来）。照返回值重试就会留下重复标签：以 `browser_get_page_tabs` 复读为准，
  不要重试创建。
- **`browser_delete_element` 可能已经 `deleted: true`，列表里却还在**（返回里的
  `stillListedIds` 就是这点）——用一次 `browser_get_page_tabs` 确认移除再往下走。
- **会话超时气泡和卡死页面是两回事**：气泡要 `browser_session(action="reconnect")` 点
  「重新连接」；`action="reload"` 是给卡住/加载过久的页面用的。混用会把超时当成卡死。
- **`browser_rename_tab` 曾按「名字前缀包含」选目标，不是精确匹配**：实测把 `name` 传成
  `GF Thin Plate` 时，被改名的是排在前面的 `GF Thin Plate literal (old)`（它**包含**该
  子串），而真正叫 `GF Thin Plate` 的标签页没动；两次连续调用因此把好好的标签页改成了
  错名字。**该缺陷已修**（2026-09-21）：`actions.resolve_exact_tab` 用标签条列表做
  **全名精确**匹配，命中数 != 1 就拒绝并在 reason 里列出全部名字与子串候选，点击走命中
  标签自己的 `data-id`；`rename_tab` 与 `step_export.export_browser_step` 都走它
  （导出侧同一缺陷的症状是把根因藏成后续步骤的 URL 不匹配报错，见第 24 节）。
  改名前后仍要用返回的 `tabs` 复读确认。
- **`browser_verify_feature_parameters` 会把自己的改名当成失败**：带
  `Feature Name Template` 的行把算出来的值印在行名里，所以「改一个值」等于「改行名」。
  实测 2026-09-21 把 `TV #gf_plate_size = 0 mm` 改成 `#gf_pitch * 2`，行名变成
  `TV #gf_plate_size = 84 mm`，于是旧名字按名查 0 行，工具报
  `parametersApplied: false` 而这次改动其实成功了。现在传 `expect_row`（行名必须包含的新
  文本）即可按新行名复读，返回里会多一个 `rowRenamed` 字段。

## 22. 接受点击之后的那次读是证据、不是判据（实测 2026-09-21）

参数对话框 accept 之后立刻读特征树，可能读到 **0 行**：accept 会先把列表清空再重绘，
而同一行在随后的确认性 reload 里活得好好的。所以确认性 reload 必须**无条件**做一次
（不要用「刚才读到行了吗」来决定做不做），并把那次中间读作为 `workbenchAppeared`
证据上报，而不是作为提交判据。提交判据只有 reload 之后的行数 + 名字差集。

对话框侧的两个对应结论（表达式异步解析的 accept 门、`Feature Name Template` 行无法按
特征名寻址）见 `onshape_docs/experience/featurescript.md` 的「Driving a thin feature's
dialog」一节。

**同一类的第二个症状：重算中间态的零件表。** accept 之后立刻读**零件**列表，1 个实体
可以读成 5 个、甚至 17 个（`Part 2 … Part 17` 全都带 `edited` 类名），看上去像「切除退化
成了加料」。实测 2026-09-21：那次 insert 的 `partItems` 是 `Part 1 … Part 17`，而同一
元素上**一两秒后的第二次读**和**一次 reload 之后的读**都稳定回到 `零件数 (1)`；此后
按 22 行→23 行继续插入，最终导出的 B-rep 与基线逐族一致。所以短路径
（`verify_commit=false`）下不要用 accept 后第一次读的零件数判对错，要用**稳定态**：
第二次读或 reload 后的读。

## 23. 参数能不能中文：标签不行，id 不行，值和名字行（实测 2026-09-21）

用户问「参数能不能中文嘞」。三个位置要分开答，证据都在
`onshape_docs/experience/featurescript.md` 的「Annotation strings are ASCII-only;
body strings are not」一节（四次 deploy 的对照表）：

- **参数标签不行。** 字段名来自 `annotation { "Name" : ... }`，只允许可打印 ASCII；
  中文标签会让 precondition 分析失败，并丢掉这个自定义特征的**全部**参数规格
  （实测 deploy 2：类型名保持 ASCII，只有参数标签是中文，仍然 0 个 feature spec）。
  特征名（`"Feature Type Name"`）和行模板（`"Feature Name Template"`）同理。
- **参数 id 不行，而且必须是 CSS 安全 ASCII。** MCP 是靠
  `[data-parameter-id="<id>"]` 这种选择器填值的（`browser_tools._expect_values` /
  insert 参数校验都强制 `[A-Za-z_][A-Za-z0-9_.-]*`），id 进 CSS 选择器，中文会直接
  不匹配。
- **值可以。** 参数**值**里的字符串是 body 数据，不是标注：零件名
  （`setProperty(..., PropertyType.NAME)`）实测中文编译通过且零件列表显示中文；
  `Thin Variable` 的 `Description` 也是 string 值，所以变量行可以带中文说明。
  变量**名**（`gf_pitch`）必须是标识符，中文不行。

所以「中文参数」的可行形态是：ASCII 标签 + ASCII id + 中文说明/中文零件名。

## 24. 虚拟化的特征表：行数看表头，行集看滚动并集，读序不是树序（实测 2026-09-21）

Feature List 是虚拟列表，一次读只给你**一个窗口**。同一个 23 行元素上的两组实测：

| 读法 | 结果 |
|---|---|
| insert 调用内部的那次读 | 23 行全在 |
| 同一天 reload 之后的独立读 | 只有 18 行（尾部 5 行没渲染），但 `headerText` 仍是 `特征 (27)` |

`特征 (27)` = 23 个用户特征 + 4 个基准面（`默认几何图元` 是分组行，不计入计数），
所以：

- **行数用表头**（`特征 (N)`、`零件数 (N)`）：表头不受窗口影响，是最便宜的全量计数，
  也是「这一步到底落地了没有」的第一个判据。
- **行集用滚动并集收集器**（`_USER_FEATURE_ROWS_JS`）；它的**顺序会轮转**，只能当集合用。
  只有同一个已渲染窗口内的 DOM 顺序才是真顺序；而「薄拉伸取它前面最近一个薄草图发布的
  区域」这条规则让**先后是语义判据**（第 21 节），所以绝不能拿跨窗口拼出来的顺序推树序。

**丢失判决的重复行可以认出来。** 一次 insert 的判决在 relay 超时里丢了，但它的行**已经
落在树的那个位置**；resume 再插入的是正确的那一行，于是这个类型多出一行，而行名计数器
会**跳号**且表头比预期多 1。实测：期望 `TSR1, TE1, TSR2(第 11 步), TE2, …`，实际
`TSR1, TE1, TSR2, TSR3, TE2, TSR4, TE3, TSR5, TE4`（表头 23 = 期望 22 + 1）。
定位方式是逐个读该行参数（`browser_read_feature_parameters`，0 配额）：重复的那行参数
与相邻步骤**完全相同**（`TSR2` 与 `TSR3` 都是 z=5 / 2×2 / 36.3 / r1.15）。

**未被消费的薄草图是几何惰性的。** 薄拉伸消费的是「它前面最近一个薄草图」发布的区域，
被下一张草图覆盖的旧区域没有任何人消费。把那行孤儿草图删掉后重新导出 STEP，B-rep 与
删前**逐族相同**（体积 `39547.5903` mm³、面积 `20002.2154` mm²、194 面、45° 锥面三族
37.32/223.5216/415.1424）。删除前仍要读一次参数，确认它确实没有被某个后续拉伸消费。
因此重复对里删**靠前**的那条是安全的，删掉被某个拉伸消费的那条会让**那个拉伸报错**。
实测（4U 盒子）：`TS 6` 读回 `41.5 × 41.5, R3.75, z=4.75`，与消费者 `TS 7` 完全一致，
删掉 `TS 6` 后树是干净的 23 行。

## 25. 页面没渲染出来，就不是关于特征的证据（实测 2026-09-21）

插入接受后，工具会**重载页面**来证明行留在工作区（§22）。但重载后的页面不是立刻可读的：
长会话里这次重载可能让 Onshape 外壳 **30 s 以上**不渲染——文档标签条与特征列表**同时为空**；
而**空闲重载**同一文档只要 **3–6 s**，浏览器重启后同一步的外壳在 **1139–2004 ms** 内就绪。
于是「存活等待」被耗在应用启动上：23 步构建的每一步都报 `inserted: false`，而行其实都已提交。

修复在 `verify_insert_committed`：重载与 `wait_for_feature_rows` 之间加一道**外壳门**
`wait_for_document_ready`，判据是文档标签按钮 `.document-tabs-button` 存在，预算
`DOCUMENT_READY_TIMEOUT_MS = 45_000`。外壳没就绪时给出**明确的未判定**而不是假失败：
`inserted: null`、`applyState: "pending_verification"`、`commit.bootReady: false`
（`appeared=false` 的提前返回路径是 `bootReady: null`），理由文本单独说明「had not
rendered … neither success nor failure」。`dev/tests/test_browser_apply_path.py` 的
`test_a_slow_post_reload_boot_is_a_non_verdict_not_a_missing_row` 钉住这条：外壳未就绪时
连存活行等待都不会发出（等待序列里只有再生等待的行选择器与外壳门的 `.document-tabs-button`）。

规则：**页面没渲染出来，不构成关于特征的任何证据**——「数不到」不等于「没有」。

## 26. 被拒绝的插入会留下打开的参数对话框和一行（实测 2026-09-21）

`browser_insert_custom_feature` 的**拒绝路径不是干净的**：下拉点击**已经**把行加进了树，
而拒绝（参数填充不满足、对话框未接受）时**参数对话框不会自动关闭**，那行保留对话框默认值
并在重载后存活（代码注释的原话：must be deleted, not ignored）。两个后果：

- `browser_read_feature_parameters` 在已有对话框打开时**读不到东西**：它只从自己打开的
  对话框读（对话框字段显示的是「最后输入」的值而不是已持久化的值），此时返回 `read: false`、
  `retryable: true`，理由要求先清掉对话框；只有 `allow_reload=true` 才允许它用一次有界
  重载丢弃面板再读。
- 因此对同一特征再插一次可能留下**重复行**（本次 4U 盒子出现了 3 条重复薄草图，其中一条
  就是被拒收后仍留在列表里的挂起行）。

规则：**读之前先清掉对话框（或重载）**；**拒绝之后立刻看到的行还不算已证明**——它可能是
默认值的悬挂行，要么删除，要么当作待证状态。

## 27. 自适应等待会长过一次 MCP 调用（实测 2026-09-21）

再生等待与存活等待的预算随元素的**自定义特征数 N** 增长（`partstudio_wait_budget_ms`：
`baseMs + perFeatureMs × N`）：

| 等待 | 实测公式 | 常量 |
|---|---|---|
| 再生（accept 后） | 30 s + 2 s × N | `PARTSTUDIO_REGENERATE_WAIT` |
| 存活（reload 后） | 30 s + 8 s × N | `PARTSTUDIO_RELOAD_WAIT` |

到第 **22** 个特征时两者已达 **74 s / 206 s**，远超单次调用的 **~60–70 s** 传输窗口，
所以**完整校验路径会跑出一次调用**（返回 no verdict，而不是 `inserted: false`）。

规则：**大树上有意走短路径**（`verify_commit=false`，本次每步 5–15 s 返回、
`readbackOk: true` 并给出新行名），**事后用一次稳定的特征树复读证明结果**，最好再补一次
几何导出验收（如 §17 的几何包质心/体积断言）——短路径的 `inserted` 是 `null`，不是判据。
