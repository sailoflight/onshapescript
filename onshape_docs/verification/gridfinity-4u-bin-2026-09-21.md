# Gridfinity 4U 高盒子：同文档特征树构建 + 解析值级 B-rep 验收（2026-09-21）

## 1. 这次要验证什么

用户要求：**重启桥之后，在同一个文档里做一个 Gridfinity 的 4U 高盒子，验证工具链正常**
（原话先误写成「4U 的盒子」，随即更正为「gridinfinity 的 4U 高盒子」，所以本页是收纳盒，
不是 19 吋机箱——前者另见 `4u-box-2026-09-21.md`）。

本页记三件事：

1. **工具链端到端正常**：夹具驱动 → 7 个变量 → 8 组「草图 + 拉伸」（4 增料 + 4 切除）→
   STEP 导出，全程浏览器腿，Onshape REST 配额 **0**；
2. **几何与解析公式逐位相等**（第 5 节：体积 `14882.3969 mm³`，不是「接近」）；
3. **本次暴露并修掉的 3 个工具缺陷**（第 7 节），其中第 1 个是本页最有价值的部分。

## 2. 目标身份

| 项 | 值 |
|---|---|
| documentId / workspaceId | `1ef2be8f3d45e6f996af24ab` / `bac7c0bf31912a956c44d15a` |
| Part Studio elementId | `59f6cc99890dd2fea26d5471` |
| 标签名（中文） | `GF 4U 盒子` |
| 行数 | 23 用户特征（`特征 (27)` = 23 + 4 基准面），**无 `hasError`** |
| 实体 | `零件数 (4)` = 4 段增料各自成体（见第 6 节） |
| 夹具 | `dev/fixtures-capture/gridfinity-4u-bin.json`，sha256 `9d34f8d397c58200d94b2cd8b6a50420714abdafbd32e8b57786b19e4aa65b40` |
| STEP | `onshape_browser_mode/outputs/step_exports/gf-4u-bin-59f6cc99-1/model.step`，sha256 `b9ec383f722ebd812fc92fa5edb08ecb3987919033453a67ee2cd0518861c057`（AP242, mm） |
| 导出清单 | 同目录 `step-manifest.json`；导出结果 `apiRequests: 0` |

## 3. 特征树（夹具 23 步 = 7 变量 + 8 组）

UI 行名即下表的 `name` / `description`；尺寸里带 `#` 的是表达式，**行上显示的是求值后的数字**。

```text
TV #gf_pitch = 42 mm   格距：相邻单元格中心距
TV #gf_gap   = 0.5 mm  每单元总间隙（单侧 0.25）
TV #corner_r = 3.75 mm 盒体外圆角半径
TV #base_h   = 7 mm    1U 底脚高（含加强段）
TV #bin_h    = 28 mm   4U 盒体高（含底脚）
TV #lip_h    = 4.4 mm  堆叠唇高（位于盒体之上）
TV #wall_t   = 0.95 mm 壁厚（内圆角 2.8）

TS 1 / TE 1  底脚    35.6 R0.8 @ z=0    +0.8      45° 底脚斜面
TS 3 / TE 2  锁扣    37.2 R1.6 @ z=0.8  +1.8      竖直
TS 5 / TE 3  外扩    37.2 R1.6 @ z=2.6  +2.15     45° 展开到 41.5 R3.75
TS 7 / TE 4  盒体    41.5 R3.75 @ z=4.75 +27.65   45.5 − 4.75（顶到 32.4）
TS 8 / TE 5  内腔    39.6 R2.8 @ z=7     −21       subtract（内底 z=7）
TS 9 / TE 6  唇斜面  36.3 R1.15 @ z=28   −0.7      subtract，45°
TS 10 / TE 7 唇锁扣  37.7 R1.85 @ 28.7   −1.8      subtract，竖直
TS 11 / TE 8 唇外扩  37.7 R1.85 @ 30.5   −1.9      subtract，45° → 顶部收成尖边
```

设计尺寸（kennetek/gridfinity-rebuilt-openscad 为准）：`GRID_DIMENSIONS_MM=[42,42]`、
`TOLLERANCE=0.02`、`BASE_HEIGHT=7`（1U）、`BASE_TOP_DIMENSIONS=[41.5,41.5]`、
`BASE_TOP_RADIUS=3.75`、`BASE_BOTTOM_RADIUS=0.8`、`d_wall=0.95`、`STACKING_LIP_HEIGHT=4.4`；
总高 `4×7 + 4.4 = 32.4`。

两个关键字面走 `#变量` 表达式，`expect_values` 确认**解析后的数值**（对话框稳定后显示的是
求值结果，不是 `#表达式` 本身）：盒体草图 `width/height 41.5 mm`（`#gf_pitch - #gf_gap`）、
`corner_radius 3.75 mm`；内腔草图 `39.6 mm`（`#gf_pitch - #gf_gap - 2 * #wall_t`）、
`2.8 mm`（`#corner_r - #wall_t`）；拉伸深度 `27.65 mm`（`#bin_h + #lip_h - 4.75 mm`）。

## 4. 薄特征的树序语义（夹具成立的前提）

「薄草图」发布一个区域，「薄拉伸」消费**它前面最近的一条薄草图**的区域。因此：

- 每组必须严格 `草图 → 拉伸` 紧邻排列，树序即几何语义；
- 未被消费的薄草图**对几何完全无影响**（第 7.3 节据此安全删掉了重复行）；
- **每条增料拉伸各自产生一个实体**，所以 `零件数 (4)` 与 4 段增料一一对应，4 段面面贴合
  （上一段末端截面 = 下一段起始截面），体积之和等于整体解析体积。

## 5. 解析值级验收：体积逐位相等

解析式用圆角矩形精确面积 `A(w,r) = w² − (4−π)r²` 沿 z 积分（45° 段 w、r 同时线性变化，
积分被 Simpson 精确求出）：

| 分量 | 体积 mm³ |
|---|---|
| 外实体（4 段叠加） | 54151.0132 |
| 内腔 | −32790.0318 |
| 堆叠唇 3 次切除 | −6478.5844 |
| **盒子总体积** | **14882.3969** |

导出的 STEP 实测：

```json
{ "volumeMm3": 14882.3969, "surfaceAreaMm2": 21369.6862,
  "boundingBoxMm": { "x": [-20.75, 20.75], "y": [-20.75, 20.75], "z": [-0.0, 32.4] },
  "faceCount": 73,
  "horizontalPlaneZs": [0.0, 0.8, 2.6, 4.75, 7.0, 28.0] }
```

体积**四位小数完全相同**。这一个数字就同时锁住了：4 段截面的宽度/圆角、两处 45° 斜面、
内腔截面与深度、以及唇部三次切除的全部尺寸——任一处错，体积都会偏。

面族与 z 区间也逐项对上（`measure` 对锥面是半角、对柱面是半径）：

| 族 | 数量 | 半径/半角 | z 区间 |
|---|---|---|---|
| 平面 | 41 | — | 面积 20193.4916（含全部竖直壁） |
| 锥面 | 4 | 45°，R0.8 | 0 → 0.8（底脚斜面） |
| 锥面 | 4 | 45°，R1.6 | 2.6 → 4.75（盒体外扩） |
| 锥面 | 4 | 45°，R1.15 | 28 → 28.7（唇斜面） |
| 锥面 | 4 | 45°，R1.85 | 30.5 → 32.4（唇外扩） |
| 圆柱面 | 4 | r1.6 | 0.8 → 2.6（锁扣） |
| 圆柱面 | 4 | r1.85 | 28.7 → 30.5（唇锁扣） |
| 圆柱面 | 4 | r2.8 | 7 → 28（内腔角） |
| 圆柱面 | 4 | r3.75 | 4.75 → 32.4（盒体角） |

`faceCount 73` 可以手工复原，说明拓扑也正确（4 个实体）：

```text
底脚段 z0→0.8    : 上下面 2 + 4 直壁 + 4 锥角 = 10
锁扣段 z0.8→2.6  : 10
外扩段 z2.6→4.75 : 10
盒体段           : 底 1 + 外壁 8 + 内底 1 + 内壁 8
                 + z=28 唇下环面 1 + 唇内三面 24 = 43
                   ------------------------------------
                   10 + 10 + 10 + 43 = 73  ✓
```

**水平面只有 `0 / 0.8 / 2.6 / 4.75 / 7 / 28`**：`z=28` 是唇的环形下表面（槽口处的台阶），
而 `z=32.4` 没有面——唇外扩与盒体外壁在同一条棱上相交，顶部是**尖边**，与设计一致。
`z=28.7 / 30.5` 也没有面，因为唇内表面是一条连续曲面（锥→柱→锥），转折处只有棱。

## 6. 与底板的互操作（落座间隙）

底脚外表面与底板插槽的间隙（单侧）：

| z | 盒脚 | 宽度间隙 | 半径间隙 |
|---|---|---|---|
| 0.0 | 竖直 35.6 | 0.70 | 0.35 |
| 0.8 | 锁扣 37.2 | 0.50 | 0.25 |
| 4.75 | 外扩 41.5 | 0.50 | 0.25 |

唇的内表面半径族是 **36.3 (R1.15) → 37.7 (R1.85) → 41.5 (R3.75)**，与底板插槽
（36.3 (R1.15) … 42.0 (R4.00)，即 `socket_bottom_radius 2.3 − offset 1.15`）**同族**，
所以另一个盒子的底脚能落进这个唇里 → 可堆叠。唇底处壁厚 `(39.6−36.3)/2 = 1.65 mm`，
唇以下壁厚 `0.95 mm`（= `#wall_t`）。

## 7. 本次暴露的 3 个工具缺陷与修复

### 7.1 接受后的重载把「应用启动」当成了「特征没提交」（已修）

插入接受后，工具会重载页面以证明行留在工作区。长会话里这次重载可能让 Onshape 外壳
**30 s 以上**不渲染（标签条与特征列表都空），而**空闲重载**同一文档只要 3–6 s；浏览器重启后
同一步的外壳在 **1139–2004 ms** 内就绪。于是「存活等待」被耗在应用启动上，每一步都报
`inserted: false`，而实际上行都提交了。

修复（`onshape_browser_mode/actions.py`）：重载与 `wait_for_feature_rows` 之间加一道
**外壳门** `wait_for_document_ready`（判定「文档标签按钮存在」，预算 45 s），并且启动未就绪
时给出**明确的未判定**而不是假失败：`inserted: null`、`applyState: "pending_verification"`、
`commit.bootReady: false`（提前返回路径为 `null`），理由文本独立。
规则：**页面没渲染出来，不构成关于特征的任何证据。**

### 7.2 表达式参数必须给 `expect_values`，否则整步被拒

`browser_insert_custom_feature` 对任何含 `#` 的参数值，要求同一参数 id 出现在 `expect_values`
（声明它必须求值成多少），因为稳定后的控件显示的是求值结果。夹具最初漏了 `height`，
第 13 步被拒：`unstatedExpressionKeys: ["height"]`。已补齐（第 3 节列出全部三处）。

### 7.3 客户端超时留下的重复行（惰性，可安全删除）

`MCP error -32001: downstream_timeout` 是客户端放弃，服务端调用仍在继续，行可能在超时报错
**之后**才落地。本次因此出现 3 条重复薄草图（其中一条来自被拒收后仍留在列表里的挂起行——
被拒收时参数对话框不会自动关闭）。处理与依据：

1. 读真实特征列表；删除所有超出检查点已完成计数的行（否则续跑会变成重复）；
2. 重复对里**靠前**的那条是惰性的（拉伸消费的是**最近的前一条**薄草图，见第 4 节），
   删除安全；删除被消费的那条会让拉伸报错——所以删前用 `browser_read_feature_parameters`
   读回参数，确认两条参数完全相同（本次 `TS 6` 读回 `41.5 × 41.5, R3.75, z=4.75`，与消费者
   `TS 7` 完全一致）。

最终树是干净的 23 行：`TS 1, TE 1, TS 3, TE 2, TS 5, TE 3, TS 7, TE 4, TS 8, TE 5,
TS 9, TE 6, TS 10, TE 7, TS 11, TE 8`，每个拉伸紧跟自己那条草图。

### 7.4 附带约束：自适应等待会超过一次传输预算

再生/存活预算随特征数增长（实测公式：再生 = 30 s + 2 s×N，存活 = 30 s + 8 s×N）。
到第 22 个特征时已达 74 s / 206 s，远超单次调用的 ~60–70 s 传输窗口，所以**完整校验路径
会跑出一次调用**。本次后半程改用短路径（`verify_commit=false`，每步 5–15 s 返回、
`readbackOk: true` 且给出新行名），最终证明由**稳定态特征树读取 + STEP 导出**承担——
这是第 5 节存在的意义。另注：运行器把检查点的夹具指纹绑定为夹具 sha256，**改夹具即作废
检查点**（`Project fixture changed after checkpoint creation`）；且 `TOOL_OUTCOME_KEYS` 要求
每步有一个真值结果键，所以 `inserted: null` 的短路径步骤无法满足运行器完成门。

## 8. 中文行名落地（2026-09-21 追加）

用户要求「我其实就是 UI 上显示中文就行」，所以本次把中文说明做进**行文本**：三个几何薄特征的
`Feature Name Template` 以 `#description` 开头，变量行保持 `###name = #value #description`。
`dev/fixtures-capture/thin-native-features.fs` 新增 `Description (row prefix)` 参数
（`definition.description is string;`，位于参数表第一项），23 步夹具全部带上中文说明。

- **能力已端到端证明**：新 FeatureScript 提交进 `Thin Native Features`（22072→25545 字节、
  0 error / 0 notice、`deployed: true`、`compiled: true`、`commitAccepted: true`），随后在
  `GF 4U 盒子` 里插入两条演示行，渲染为
  `TS 底脚平面 35.6 mm x 35.6 mm @z=0 mm` 与 `TE 底脚斜面 45° 0.8 mm`。
- **演示行已删除**，元素回到 23 个用户特征（表头 `特征 (27)` = 23 + 4 基准面）、
  `零件数 (4)`、所有行 `hasError: false`。几何未受影响：本次编辑只改 FeatureScript 的
  行模板与参数声明，既有的 16 个几何行不重算。
- **行名在再生之后才定型**：接受点击时读到的是占位值（`100 mm x 100 mm`、`10 mm`），
  再生后才是 `35.6 mm x 35.6 mm`、`0.8 mm`。所以短路径步骤的行名不能当验收证据。
- 夹具级守卫新增 4 条（中文说明存在、几何模板 `#description` 前置、变量行 `#value` 在前、
  `definition.description is string;` 条数 == `defineFeature(` 条数）。

## 9. 复现

```bash
# 夹具 → 浏览器（文档内新建 Part Studio 后，把标签名设为 GF 4U 盒子）
# 逐段插入：7 个 Thin Variable + 8 组 Thin Sketch Rectangle / Thin Extrude
# 导出（0 REST 配额）
#   browser_export_step  source_tab="GF 4U 盒子"  export_id=gf-4u-bin-59f6cc99-1
# 离线几何核验
/home/lijq/code/CadQ/.venv/bin/python onshape_docs/scripts/verify_step_brep.py \
  /mnt/c/MCP/onshapescript/onshape_browser_mode/outputs/step_exports/gf-4u-bin-59f6cc99-1/model.step
```

夹具级离线守卫见 `dev/tests/test_gridfinity_4u_bin_fixture.py`。

## 10. 中文行名版重建：`网格盒子 4U`（2026-09-21 追加，0 REST 配额）

第 8 节证明了「中文说明能进行名」，但它同时也说明**只有新插入的行才带中文**：既有
`GF 4U 盒子` 的 16 个几何行是在中文参数与模板落地之前插入的，birth name 永远是
`TS Thin Sketch Rectangle 1` / `TE Thin Extrude 1` 这类英文名。用户要求「重建一下」，
于是本节把同一份夹具在**新标签页**里完整重放一遍，得到中文行名的同几何模型。

### 10.1 目标身份

| 项 | 值 |
|---|---|
| 标签名（中文） | 网格盒子 4U |
| elementId | `a3cf38f64376156ef242dba3` |
| 文档 / 工作区 | `1ef2be8f3d45e6f996af24ab` / `bac7c0bf31912a956c44d15a` |
| 行数 | **23 用户特征**（`locatorRows: 23`：7 变量 + 8 薄草图 + 8 薄拉伸），无 `hasError` |
| 实体 | 零件数 (4) = 4 段增料各自成体 |
| 旧页 | `GF 4U 盒子`（`59f6cc99890dd2fea26d5471`）**未改动**，英文行名仍在 |

### 10.2 落地方式（夹具逐行重放，短路径）

夹具 `dev/fixtures-capture/gridfinity-4u-bin.json` 早已是中文版（第 8 节把它整份补上了
`description`），所以**不需要改夹具**：23 步原样重放，只把 `part_studio_tab` 指向新标签页。

- 每步一次 `browser_insert_custom_feature`，`verify_commit=false`（第 7.4 节：23 行时
  再生预算 74 s、存活预算 206 s，都超过单次调用的传输窗口），`confirm_mutation=true`；
- 三个含 `#变量` 表达式的步骤带上夹具的 `expect_values`（第 13/14/15/17 步），
  实测全部解析成功：盒体 41.5 mm / 圆角 3.75 mm、外壳 27.65 mm、内腔 39.6 mm /
  2.8 mm、唇斜面 z=28 mm；
- 过程约束：浏览器动作限速 **8 次/分**，逐行调用被 `ActionRateExceeded` 挡过一次，
  之后按 ~9 s 间隔稳定推进；23 步全部一次接受。

### 10.3 行名（表内读到，即 UI 显示）

```text
TV #gf_pitch = 42 mm 格距：相邻单元格中心距
TV #gf_gap = 0.5 mm 每单元总间隙（单侧 0.25）
TV #corner_r = 3.75 mm 盒体外圆角半径
TV #base_h = 7 mm 1U 底脚高（含加强段）
TV #bin_h = 28 mm 4U 盒体高（含底脚）
TV #lip_h = 4.4 mm 堆叠唇高（位于盒体之上）
TV #wall_t = 0.95 mm 壁厚（内圆角 2.8）
TS 底脚平面 35.6 mm x 35.6 mm @z=0 mm      TE 底脚斜面 45° 0.8 mm
TS 锁扣段 37.2 mm x 37.2 mm @z=0.8 mm      TE 锁扣段竖直 1.8 mm
TS 外扩段起始 37.2 mm x 37.2 mm @z=2.6 mm  TE 外扩段斜面 45° 2.15 mm
TS 盒体 41.5 mm x 41.5 mm @z=4.75 mm       TE 盒体外壳 27.65 mm
TS 内腔 39.6 mm x 39.6 mm @z=7 mm          TE 内腔切除 21 mm
TS 唇斜面起始 36.3 mm x 36.3 mm @z=28 mm   TE 唇斜面切除 45° 0.7 mm
TS 唇锁扣 37.7 mm x 37.7 mm @z=28.7 mm     TE 唇锁扣切除 1.8 mm
TS 唇外扩起始 37.7 mm x 37.7 mm @z=30.5 mm TE 唇外扩切除 45° 1.9 mm
```

**接受点击时的行名不是证据。** 短路径下每一步的返回里，刚接受的行先渲染成占位符
（`TV Thin Variable`、随后一次读到 `TV # = 0 mm`）且 `hasError: true`；下一次读表
（或重算完成）才定型为上面的行名并 `hasError: false`。这与第 8 节「行名在再生之后才
定型」是同一条规律，本次在变量行上也复现了一次。

### 10.4 STEP 验收：与英文版逐位一致

`browser_export_step source_tab="网格盒子 4U" export_id=gf-4u-bin-cn-a3cf38f6-1`
（导出器自己报 `apiRequests: 0`），离线核验：

| 量 | 本节（中文行名版） | 第 5 节基线 |
|---|---|---|
| `volumeMm3` | **14882.3969** | 14882.3969 |
| `surfaceAreaMm2` | **21369.6862** | 21369.6862 |
| `boundingBoxMm` | x/y ±20.75、z −0→32.4 | 同 |
| `faceCount` | **73** | 73 |
| `horizontalPlaneZs` | 0 / 0.8 / 2.6 / 4.75 / 7 / 28 | 同 |
| 面族 | 平面 41（20193.4916）；锥 45° R0.8 / R1.6 / R1.15 / R1.85 各 4；柱 r1.6 / r1.85 / r2.8 / r3.75 各 4 | 同 |

体积、面积、包围盒、面数与全部面族逐项相同 ⇒ **「行名中文」与「几何不变」同时成立**，
且这次的证据是「同一夹具在另一个标签页重建出同一 B-rep」，比基线更直接。

### 10.5 复现

```bash
# 文档内新建 Part Studio → 改名「网格盒子 4U」
# 逐行重放 dev/fixtures-capture/gridfinity-4u-bin.json 的 23 步
#   browser_insert_custom_feature part_studio_tab="网格盒子 4U" verify_commit=false
#   （含表达式的步骤带 expect_values；浏览器动作限速 8/min，间隔 ~9 s）
# browser_read_feature_parameters 读回 locatorRows == 23 且行名全中文
# 导出（0 REST 配额）
#   browser_export_step source_tab="网格盒子 4U" export_id=gf-4u-bin-cn-a3cf38f6-1
/home/lijq/code/CadQ/.venv/bin/python onshape_docs/scripts/verify_step_brep.py \
  /mnt/c/MCP/onshapescript/onshape_browser_mode/outputs/step_exports/gf-4u-bin-cn-a3cf38f6-1/model.step
```

### 10.6 边界

- 本次只重放夹具、未改夹具、未改 FeatureScript、未改任何既有行的参数；`GF 4U 盒子`
  与 `网格底板 2×2` 保持原样。
- 不声明别的几何链也能这样重放：中文行名依赖 FS 的 `Feature Name Template` 以
  `#description` 开头（第 8 节），没有模板的特征仍会显示英文类型名。
- 全程 0 次 Onshape REST 调用；`browser_export_step` 走的是浏览器导出对话框。
