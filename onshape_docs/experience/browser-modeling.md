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

- **`partNames` 不可信，只有 `parts` 可用（2026-09-20 实测）**。`read_partstudio_features`
  把 `.part-list-container` 的文本按 `\s+ → 单空格` 归一化并截断到 400 字符，而
  `parse_part_summary` 按 `\s{2,}|\n` 切名字 —— 归一化之后这个切分永远不会命中，
  于是两条分支都错：`count == 1` 走特例，把整个剩余串当成一个名字（实测
  `零件数 (1) 螺旋凸棱柱 曲线数 (1)` → `["螺旋凸棱柱 曲线数 (1)"]`，把下一个分区表头
  `曲线数` 吞进了名字）；`count > 1` 直接返回 `[]` 且 `partNamesParsed: false`
  （实测 `零件数 (9)` 与 `零件数 (11)` 两次）。判定建模成功只用 `parts > 0`；
  真名字应从 DOM 按零件行元素取，而不是解析归一化后的字符串。

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
