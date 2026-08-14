# Live FeatureScript verification — 实测记录

目标：用真实 Onshape 服务器验证 `docs/verification/llm-experience-fs.md` 的
语言论断。**总预算 150 次**（100 + 追加 50）已全部用尽。

## 最终结论

**根因已定位，正确结构已确认**（探针 E、F 成功，独立最小文件 1 spec）：

1. **Feature 定义唯一正确形式**（trophy 实锤 + 探针验证）：
   ```
   annotation { "Feature Type Name" : "..." }
   export const NAME = defineFeature(function(context is Context, id is Id, definition is map)
       precondition { ... }
       { ...body... });
   ```
   precondition 块后**直接接 body 块**，整体是 `defineFeature(...)` 一次调用，
   结尾 `});`。任何"precondition 后提前 `)`、body 写在外面"的写法都是语法错误。
2. **`featureSpecs` 空数组 ≠ 编译失败**——普通函数文件（编译成功）也返回空，
   只有带 annotation 的 export feature 出现。判别："正确形式 feature" 非空，
   否则空。
3. **`libraryVersion` 恒为 0**；版本由 `.fs` 头 `FeatureScript N;` + `import
   version` 声明，无 API 可查。
4. **符号可见性跟随传递导入**：trophy 用过的符号（isLength/opExtrude/
   qCreatedBy/Z_DIRECTION/BoundingType/mm/LengthBoundSpec）已验证可见；
   isQuery/evVolume/cubicInch/vector/GBTErrorStringEnum/centimeter 等**未经验证**
   （列在 experiments.json 的 risk 标记）。

## 预算账目（本次 run，ledger 起点 25，终点 150）

| 用途 | 调用数 |
|---|---|
| 创建实验 FS + 版本探测 | 5 |
| 15 实验初跑（普通函数形式，全部误判） | 45 |
| 排查（缓存/异步/二分/对照） | 75 |
| 探针 E/F 确认正确形式 | 6 |
| **合计** | **125**（+25 旧账 = 150 ledger） |

服务器真实用量：119 基线 + 150 = **约 269/2500**。

## 血泪教训 → 静态检查器（用户要求）

约 **120 次额度**花在调试我自己写的 FS 语法错误（悬空 annotation、defineFeature
形式错误、未验证符号、空 body）。这些错误**完全可以本地零成本拦截**。因此
新增 `scripts/fs_local_check.py`（见 `docs/fs-assistant.md`）：上传前本地校验
结构 + 符号，避免坏文件上传浪费额度。

## 实验文件状态

`experiments/` 15 个文件已**改写为正确 defineFeature 形式**，符号尽量用已验证
集，未验证符号在 `experiments.json` 标注 `risk:`。**尚未在真实服务器重跑**
（预算已尽）。重跑命令：

```bash
# 修改 run_live_tests.py 的 MAX_BUDGET 后：
python3 scripts/fs_local_check.py docs/verification/live/experiments/  # 先本地拦截
python3 docs/verification/live/run_live_tests.py
```
