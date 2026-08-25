# Live FeatureScript verification — 实测记录

目标：用真实 Onshape 服务器验证 `onshape_docs/experience/featurescript.md` 的
语言论断。原始活动声明的**总预算 200 次**（100 + 追加 50 + 追加 50）已全部用尽。

> **Evidence interpretation**：本文件保留按时间追加的实验叙述，当前结论以
> `onshape_docs/experience/`、根安全规则和持久化 JSON 为准。下面的额度/ledger
> 数字是历史快照或事后重建，不是当前账户状态；与 JSON 冲突时 JSON 优先。文中命令
> 不构成重跑授权，跨版本 import 精确边界仍是 unresolved。迁移状态见
> `../../../docs/history/TRACEABILITY.md`。

> **2026-08-14 更新 — 15/15 已定案，勿重跑**：下面表格里的 ⚠/❌ 是相对当时
> 文档断言的"意外"，其结论已吸收进 `experiments.json` 的修正期望（02/05/08/15
> 改为 compile-ok：body 不编译；07/11/13 改为 compile-error：服务器上符号不存在）。
> 2026-08-14 意外实跑已对活服务器重确认 **15/15 全部符合当前期望**（FeatureScript
> 3029，45 次调用）。完整 46 次调用 trace 与"不要重跑"说明见
> [`reconfirm-2026-08-14.json`](reconfirm-2026-08-14.json)；`results.json` 顶部注记
> 解释了 `expect` 列的旧 manifest 背景。

## 最终结论（15 实验，当前期望下 15/15 符合预期）

### 最大发现：`featurespecs` 只编译签名，不编译 body

`featurespecs` 返回 1 个 spec 只证明 **annotation + precondition 签名层**
有效。**feature body 的代码（op* 调用、变量、类型标注）在"保存"时不编译**，
错误延迟到"实例化"（把 feature 插入 Part Studio）时才暴露。

这解释了全部实验结果：

| 实验 | 结果 | 说明 |
|---|---|---|
| 01 三层 q/op/ev | ✅ compile-ok | 文档断言实测证实 |
| 02 opExtrude 传标量 5 | ⚠ compile-ok | **body 不编译**：`opExtrude(..., 5)` 未在保存时报错 |
| 03 缺 context | ✅ compile-error | 函数签名（签名层）错 → 0 specs |
| 04 混合单位 5mm+2cm | ✅ compile-ok | centimeter 可见 |
| 05 量纲不匹配 5mm+2 | ⚠ compile-ok | **body 不编译**，量纲错误延迟 |
| 06 import 2960.0 | 0 specs | 结果受“无 bound-spec precondition 不发射 spec”混淆，不能据此证明版本拒绝 |
| 07 GBTErrorStringEnum | ❌ compile-error | **枚举在签名层即不存在**（服务器 3029 无此类型） |
| 08 拼错函数 qDoesNotExist | ⚠ compile-ok | **body 不编译** |
| 09 Vector 运算符 | ✅ compile-ok | vector()/norm() 可见 |
| 10 map 访问 + as | ✅ compile-ok | |
| 11 isString 谓词 | ❌ compile-error | **isString 在 3029 不存在**（is* 谓词版本间变动） |
| 12 precondition | ✅ compile-ok | |
| 13 isArray 谓词 | ❌ compile-error | **isArray 在 3029 不存在** |
| 14 Id + string | ✅ compile-ok | |
| 15 未知类型 NotARealType | ⚠ compile-ok | **body 不编译**，类型错误延迟 |

8 个 ✅ 全部是文档断言实测证实；4 个 ⚠ 揭示"保存 ≠ body 有效"；3 个 ❌ 是
真实的符号缺失（都比"文档无定义"更严重：**服务器上也不存在**）。

### 对 LLM 的直接含义

- **"编译通过"（1 spec）只验证签名/precondition。** body 的正确性只能靠
  实例化验证（POST feature 到 Part Studio），而实例化是 2-3 次额度/feature。
- **本地静态检查器是唯一的 body 层防线**：`onshape_docs/scripts/fs_local_check.py` 的
  符号 warning（qDoesNotExist、NotARealType）会在上传前标记 body 错误——
  服务器保存时不报，只能靠本地检查或花实例化额度。
- **命名即语法在签名层成立**（op*/q*/ev* 拼错会让签名检查失败）；body 层
  的拼错被延迟。

## 实例化层验证（body 真实执行；持久化结果记录 25 次调用）

5 个 feature 依次上传 → 新建 Part Studio → POST feature 实例化。**全部
`featureStatus=ERROR`**，证实 body 错误在实例化暴露：

| 文件 | 签名层 | 实例化 | 说明 |
|---|---|---|---|
| 01 三层对照 | ✅ 1 spec | ERROR | body 语法有效但运行时空查询（qCreatedBy(id) 首跑无 body）→ ERROR 无法区分编译错/运行错 |
| 02 opExtrude 传 5 | ✅ 1 spec | ERROR | body 类型错，实例化暴露 |
| 05 量纲不匹配 | ✅ 1 spec | ERROR | 同上 |
| 08 qDoesNotExist | ✅ 1 spec | ERROR | body 编译错，实例化暴露 |
| 15 NotARealType | ✅ 1 spec | ERROR | body 编译错，实例化暴露 |

**关键**：`POST .../features` 响应只有 `featureStatus`，**无错误文本**；
ERROR 的 feature 仍被保存（GET features 可见）。LLM 无法从 API 读到具体
错误，只能靠 ERROR 判断"body 未完成"再推理原因。

## 历史预算叙述（事后重建，非精确账本 authority）

下表保留原复盘分类；其 `29`、合计和终点与持久化
`instance-results.json` 等证据并不完全一致，不能用于当前配额计算：

| 阶段 | 调用数 |
|---|---|
| 初跑 + 排查（语法错误调试） | 120 |
| 探针确认正确形式 | 6 |
| 正确形式重跑 | 45 |
| 08 诊断 | 3 |
| 实例化验证 | 29 |
| eval 工具开发 + 收尾（format 试错、create/实例化补测、search 探测） | 82 |
| **合计净增** | **286**（25 → 311 ledger） |

服务器真实用量（用户在 UI 确认）：119 基线 + 311 ledger = **430/2500**
（剩约 2070）。ledger 的 `calls` 是 100 条滚动记录，末尾 82 次只能按 endpoint
类别还原，无法逐条拆分——这本身就说明：**不要把验证预算花在事后复盘上，
验证即记账（`onshape_api_quota`），不要在额度上猜测**。

## 血泪教训 → 静态检查器

约 120 次额度花在调试 FS 语法/结构错误。`onshape_docs/scripts/fs_local_check.py` 在
上传前拦截结构错误（硬错）并标记符号缺失（警告），避免同类浪费。详见
`README.md` 的 "Zero-cost syntax guard" 段。

## 实验文件状态

15 个文件为正确 defineFeature 形式，`experiments.json` 标注 expected +
symbols risk，历史结果在 `results.json`。只允许重复运行零调用的本地检查；
下面的 live runner 是历史入口，不得因本记录直接执行：

```bash
python3 onshape_docs/scripts/fs_local_check.py onshape_docs/verification/live/experiments/  # 先本地拦截
# Historical live entry only; requires a new explicit unresolved fact, approval, and budget:
# python3 onshape_docs/verification/live/run_live_tests.py --budget <approved-limit>
```

---

## 追加：`is*` 谓词集实测（2026-08-14，用户放宽额度至 500/2500）

用户授权继续验证剩余悬案，本轮 ledger 311 → 459（+148，真实用量 119+459=**578/2500**）。

方法：`onshape_docs/scripts/live_is_probe.py` 用 `onshape_eval_featurescript` 在部署运行时
（eval `libraryVersion` **3044**）逐符号/收敛探测。编译器**停在第一个错误**
→ 探测只能一次揭示一个失败符号；`isReal` 等"类型不匹配"错误会直接暴露 3044
真实签名，而 bare-reference 错误可区分"存在"（Cannot reference function X）
与"缺失"（Variable X not found）。

**结论**（`live-is-predicates.json`）：镜像 29 个 `is*` 谓词，28 个在 3044 存在
——22 个可直接调用，6 个以 2960 签名存在但需正确参数
（`isReal(value, boundSpec)`、`isSquare(matrix)`、`isTopLevelId(id)`、
`isWrap{Cone,Cylinder,Plane}(context, val)`）；**`isUvVector` 是唯一漂移**
（2960 文档列了，3044 已删，用 `isUnitlessVector`）。
`isQuery/isString/isArray/isType` 在 3044 **全部不存在**——precondition 用
`is <Type>` 语法（`definition.x is length`），不是 `isX()` 调用。

**代价教训**：当时旧 resolver 在探针未传 `part_studio_id` 时会隐式遍历文档，
造成大量额外调用；该行为后来已移除。当前 resolver 只接受显式 id 或已有缓存，
二者都没有就会在网络前失败。历史调用估算保留在本记录中，不得当作当前行为；
当前规则见 `onshape_docs/experience/featurescript.md` 的 eval 小节。

---

## 追加：gap-probe 收尾（2026-08-14；精确结果以 JSON 为准）

原叙述称分两次运行并使用 22 次预算；持久化 `gap-probe-results.json`
记录的是 budget 12、各结果合计 13 次。该差异保留为历史账目误差，不据此推断
当前 guard 或额度。

**A. 语言特性 eval（runtime 3044，每次恰好 1 调用，全部 ✅ errors 空）**
- `concat_units_trig`：`"part" ~ 3` → "part3"；`(5*mm)/2` → 0.0025 m；
  `sin(90*degree)` → 1.0；`10*inch + 1*inch` → 0.2794 m。单位运算 + 三角函数
  角度制实测成立。
- `control_flow`：`for-in`、`while`、`for (k, v in map)`、lambda 赋值全通过，
  结果 [9.0, 42.0, 3.0] 逐项精确。
- `query_typecheck`：`q is Query` → true；`qNthElement(q, 0)` 返回 NTH_ELEMENT
  查询结构（qCreatedBy 的实体类型/filter 全链路）。

**B. render_preview（唯一零真实调用记录的工具）✅**：iso 300×300 → 57927 字节
PNG（sha256 d676c853…），1 调用。渲染通路端到端可用。

**C. 跨版本 import 边界 —— 探测仍有缺陷，上界未测出；但 spec 发射机制已定位**
3029/3044/3035 三个 import 版本全部 `specCount:0` + `errorType/errorMessages`
全空 + 上传非 4xx → 编译器都**接受**了这些 source（import 版本 ≤ 运行时 3044
兼容）。0 specs 不是"接受"的证据，但 symbol-sweep 补出的对照把它解释清楚了：
**feature spec 只对 precondition 里带 bound spec 的参数发射**（实验
01/02/04/05/08/09/10/12/14/15 全部 1-spec，precondition 全部有
`{ (millimeter) : [...] } as LengthBoundSpec`）；裸 `isLength(definition.size)`
无论 body 读不读 definition 都是 0 specs（sweep 的 import 探测 body 用
`opExtrude(... "endDepth" : definition.size)` 仍 0 specs——证明**body 无关**，
纠正了本轮早先"body 读参数才发射"的推断）。

由此**实验 06 的旧结论进一步被混淆**："import 旧版本 2960.0 是签名层错误"——
06 根本没有 precondition（无 bound spec），0 specs 完全可由"无参数 UI"解释，
未必是版本拒绝。仍成立的签名层 0-spec 案例：缺 context（实验 03）、precondition
引用不存在的符号（07/11/13）——这些是真实编译失败。修复：import probe 的
precondition 已改为带 bound spec（`isLength(definition.size, { (millimeter) :
[1,2,3] } as LengthBoundSpec)`），这样"接受"→1 spec、"版本拒绝"→0 specs +
errorType。上界（import > 服务器，3050）仍未测出，需再跑一次修正后的探测。

**D. REST 只读端点（getDocument / getDocumentVersions / getDocumentWorkspaces）**
**未跑到**——C 分区耗掉 9 次后预算尽。已把 D 提到 C 之前，保证 3 次只读必跑。

**配额账目**：ledger 469 → 482（+13；本轮 spent 13/12），真实 = 119 + 482 =
**601/2500**（剩 ~1899）。

---

## 追加：symbol-sweep 与 import 边界候选证据（2026-08-14）

`onshape_docs/scripts/live_symbol_sweep.py` 后来加入时间戳、增量落盘、断点续跑、
自适应预算、节流和 429 停止策略。首轮结果未增量保存，因此本段中的部分 run/调用
叙述没有对应持久化行。当天 `Retry-After`/remaining 数字是已解除的历史限流快照。

**import 边界（unresolved）**：历史叙述将实验 3029 的 1 spec 与两次未持久化的
3044 0-spec 结果对比，提出 `3029 < version <= 3044` 的候选边界。但后续持久化
`gap-probe-results.json` 和 `live-symbol-sweep.json` 未形成同一 bound-spec 形状下
3029 接受、3050 拒绝的配对证据，且 0 specs 会被 spec 发射条件混淆。因此这些结果
只支持“版本边界可能存在”的假设，不证明精确边界或静默拒绝。当前 authority 必须
将精确边界报告为 unknown；只有实际任务需要该唯一事实、且获得新的 live 权限和
硬预算时，才设计一次可持久化的配对探针。

**429 策略（用户 2026-08-14 指令，已实现）**：`client.request` 对 429 **永不重试**
——立即抛 `RateLimited`（等待时间已写入 ledger 的 `lastRetryAfter`）；所有额度
脚本（sweep/gap_probe/is_probe/run_live_tests/run_instance_tests）重新抛出
RateLimited 而非吞掉继续，脚本把错误写入结果文件并退出，**严禁重试、严禁跳过
下一任务**。硬额度预算：每脚本 `--budget`（总额上限）+ preflight 对年额度 +
import 每次版本探测前检查剩余 ≥ 3 次调用。

