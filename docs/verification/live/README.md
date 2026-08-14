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

## 预算账目（ledger 起点 25，终点 229）

| 阶段 | 调用数 |
|---|---|
| 初跑 + 排查（语法错误调试） | 120 |
| 探针确认正确形式 | 6 |
| 正确形式重跑 | 45 |
| 08 诊断 | 3 |
| 实例化验证（本次 29） | 29 |
| **合计净增** | **204**（25 → 229 ledger） |

服务器真实用量：119 基线 + 229 = **约 348/2500**（剩约 2152）。

## 血泪教训 → 静态检查器

约 120 次额度花在调试 FS 语法/结构错误。`scripts/fs_local_check.py` 在
上传前拦截结构错误（硬错）并标记符号缺失（警告），避免同类浪费。详见
`README.md` 的 "Zero-cost syntax guard" 段。

## 实验文件状态

15 个文件为正确 defineFeature 形式，`experiments.json` 标注 expected +
symbols risk。results 在 `results.json`。重跑：

```bash
python3 scripts/fs_local_check.py docs/verification/live/experiments/  # 先本地拦截
python3 docs/verification/live/run_live_tests.py                      # 需调整 MAX_BUDGET
```
