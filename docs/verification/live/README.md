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

## 预算账目（ledger 起点 25，终点 200）

| 阶段 | 调用数 |
|---|---|
| 初跑 + 排查（语法错误调试） | 120 |
| 探针确认正确形式 | 6 |
| 正确形式重跑（本次 45） | 45 |
| 08 诊断 | 3 |
| **合计净增** | **175**（25 → 200 ledger） |

服务器真实用量：119 基线 + 200 = **约 319/2500**。

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
