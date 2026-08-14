# Live FeatureScript verification — 实测记录

目标：用真实 Onshape 服务器验证 `docs/verification/llm-experience-fs.md` 的
语言论断。**总预算 200 次**（100 + 追加 50 + 追加 50）已全部用尽。

## 最终结论（正确形式重跑，15 实验，8/15 符合预期）

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
| 06 import 2960.0 落后版本 | ✅ compile-error | 版本不匹配是签名层错误 |
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
- **本地静态检查器是唯一的 body 层防线**：`scripts/fs_local_check.py` 的
  符号 warning（qDoesNotExist、NotARealType）会在上传前标记 body 错误——
  服务器保存时不报，只能靠本地检查或花实例化额度。
- **命名即语法在签名层成立**（op*/q*/ev* 拼错会让签名检查失败）；body 层
  的拼错被延迟。

## 实例化层验证（body 真实执行，预算 100，实花 29）

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

## 预算账目（ledger 起点 25，终点 311）

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

约 120 次额度花在调试 FS 语法/结构错误。`scripts/fs_local_check.py` 在
上传前拦截结构错误（硬错）并标记符号缺失（警告），避免同类浪费。详见
`README.md` 的 "Zero-cost syntax guard" 段。

## 实验文件状态

15 个文件为正确 defineFeature 形式，`experiments.json` 标注 expected +
symbols risk。results 在 `results.json`。重跑：

```bash
python3 scripts/fs_local_check.py docs/verification/live/experiments/  # 先本地拦截
python3 docs/verification/live/run_live_tests.py --budget 50           # 每轮预算用 --budget 指定,preflight 护栏
```

---

## 追加：`is*` 谓词集实测（2026-08-14，用户放宽额度至 500/2500）

用户授权继续验证剩余悬案，本轮 ledger 311 → 459（+148，真实用量 119+459=**578/2500**）。

方法：`scripts/live_is_probe.py` 用 `onshape_eval_featurescript` 在部署运行时
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

**代价教训**：探测循环没传 `part_studio_id` 时，`resolve_part_studio_id` 每次
eval 会走整个文档（elements GET + 每 Part Studio 一个 parts GET ≈ 10 调用），
首轮 33 符号探测白烧约 126 次；显式传 id 后每次恰好 1 调用（收敛探测 33 符号
共 12 次）。教训已写入 `llm-experience-fs.md` 的 eval 小节。
