# Onshape MCP 开发：API 配额保护与测试优化

> 所有代理先读取根目录 `AGENTS.md`。以下检索顺序是硬约束，不得用模型记忆替代本地证据。

## 遇到问题的强制检索顺序

1. 先分类：项目流程、FeatureScript、REST API、浏览器经验或源码实现。
2. 先查最小索引：`docs_search/docs_list`、`fs_search/fs_quick_reference`、
   `onshape_api_search/onshape_api_list_tags` 或源码内容搜索。
3. 再读一个精确条目：`docs_section`、函数、类型、guide section、endpoint、schema
   或匹配到的函数及测试。
4. 只有结构化条目不足时，才读完整 Markdown、标准库源码、OpenAPI 或 `reference/raw/` 原文。
5. 收集证据以后才开始推理、计划和修改；可以查到的名称、签名、payload、selector、流程禁止猜测。

固定顺序：**先查后想，先索引后精确条目，最后才是完整原文**。

## 大索引保护

`onshape_docs/index.json` 约为 159 KiB 量级（重建后大小会变化）。禁止为了回答一个问题
把整个文件一次性放入模型上下文。优先调用 `docs_search/docs_list` 找候选，再用
`docs_section` 读取一个精确小节。查询工具不可用时，只用 `grep`/`rg` 定位关键词、
page id、路径或标题，然后从 authored Markdown 读取命中附近的有界行窗口；禁止输出
或吞入完整 JSON。其他大型索引、OpenAPI、标准库和 `reference/raw/` 同样遵守
“候选搜索 → 有界局部读取 → 必要时原文”的顺序。

> Onshape 真实 API 账户只有约 **2500 次/年**调用额度，是**不可再生稀缺资源**。
> 开发目标：在尽可能接近 **0 次真实调用**的情况下完成开发、修复、重构、测试；
> 只有当某个事实无法靠文档/现有代码/静态分析/Mock/Fixture/历史响应确定时，
> 才允许最少量真实请求。任何可离线完成的验证，都不得调用真实 Onshape API。

## 最高约束

- 真实 API 请求必须是**显式行为**，不是脚本默认行为。默认 `LIVE_API_ENABLED = false`。
- 一次真实请求只购买一个"无法离线获得的新事实"；买到以后**永久保存为 fixture**，
  让未来所有开发与测试都能离线重现。
- 当"快速调试"与"节省额度"冲突时：**优先保护 API 年度额度**。
- Onshape API 不是开发调试环境。

## 硬约束（违反即烧额度）

1. **禁止试错式 API 开发**：不许 `发送 → 400 → 猜参数 → 再发`。必须先
   `文档 → schema → 现有实现 → 本地构造请求 → 静态验证 → mock`，最后只发送一次
   最可能正确的请求。真实 API 不得充当调试器。
2. **每次 live 请求前必须有明确假设**：写明"要验证的唯一事实"（如"POST 该 payload
   返回 200 且含字段 bar"）。说不出就**不要发送**。
3. **请求预算**：默认 `expected_live_requests = 1`、`max_live_requests = 1`。
   超过 1 次先重新设计测试。**GET == POST == PATCH == DELETE**，都消耗额度。
4. **禁止自动 retry**：
   - 429 **永不重试**——`client.request` 立即抛 `RateLimited`（等待时间在
     `onshape_rest_api_mode/config/api-usage.json` 的 `lastRetryAfter`；可能达 ~20h）。所有 live 脚本
     重新抛出 RateLimited，错误写结果文件并**退出**，严禁吞掉后跳过下一任务。
   - **POST/PATCH/DELETE 对 5xx/超时也不重试**——超时≠未执行，重复发送可能
     重复执行变更。
5. **禁止隐式 lookup**：高层工具不得偷偷 `GET documents → workspaces → elements → …`。
   显式传 id，或用缓存/fixture/前次操作结果。`onshape_eval_featurescript` 不带
   `part_studio_id` 时 `resolve_part_studio_id` 会走整个文档 ≈ 10 次/调用——**必须显式传**。
6. **禁止"写后再读"**：不默认 `POST → GET 确认 → GET 列表`。POST 响应够用就用。
7. **不自动 cleanup、不自动分页**：用固定测试 Document/Workspace；分页前先计算
   最大请求数并设硬上限。
8. **缓存稳定 metadata**（documentId/workspaceId/elementId/…）：`onshape_rest_api_mode/config/onshape-state.json`。
   刷新必须是显式动作，不隐式重新查询。

## 调试顺序（遇问题严格按序，不得跳步）

```
1 分类问题并查对应索引     6 Mock 测试
2 阅读匹配实现与已有测试   7 Replay 历史响应
3 读取一个精确文档条目     8 Dry-run 构造最终 HTTP 请求
4 必要时才读完整原文       9 判断是否仍无法离线确定
5 检查 fixture 并静态分析  10 才执行最少量 Live 请求
```

## 沉淀与复用

- 每次确实执行的 live 调用必须产出可复用 fixture：
  method / path / query / 脱敏 request headers / request body / status /
  脱敏 response headers / response body / 时间 / 测试目的 →
  `dev/tests/fixtures/onshape/<operation>/request.json + response.json + metadata.json`。
  以后相同场景**只 replay，不再请求真实服务器**。
- 敏感信息（API Secret / Access Key / Authorization / Cookie / Token）一律
  `<REDACTED>`，禁止进 fixture、日志、测试输出。
- **正式代码与测试共享同一套** request builder / serializer / transport /
  response parser——不得维护两套，否则测试证明的只是测试脚本正确，不是 MCP 正确。
- 优先 MockTransport / ReplayTransport；大多数测试应只验证
  `build_request()` + `parse_response()`（method/url/params/headers/body/schema），
  不碰服务器。

## 成本标注与 dry run

- 工具应暴露成本特征：`network: offline|live`、`estimated_requests`、
  `max_requests`、`mutating`、`cacheable`。LLM 优先选 0 请求工具。
- 写操作应支持 `dry_run=true`：构造与正式请求**完全相同**的请求，不发网络请求，
  输出 method / URL / body / 预计请求数。只有 Dry Run 通过后才考虑 Live。

## 本仓库现状（2026-08-14 记账）

- **`LIVE_API_ENABLED` 显式开关已全量接入**（协议最高约束，默认关闭）：`live_blocker` /
  `BudgetGuard` / 示例脚本 `examples/.../scripts/_guard.py` / `fetch_onshape_api.py` /
  各 live 脚本在发任何请求前检查；未设 flag 即拒绝并退出（0 网络）。dry_run 与离线
  工具不受影响。单元测试在 `dev/tests/test_quota_guards.py`。
- 2026-08-14 的突发限流（`Retry-After 72910s`/`Rate-Limit-Remaining 0`）**已解除**：
  ledger 现报 `Rate-Limit-Remaining 2987`，实测请求成功；`lastRetryAfter 72910` 是过期
  残留，勿据此认为账户被 hold。切勿为了"验证 hold 门"而设 `LIVE_API_ENABLED=1` 真跑
  ——验证门逻辑只用 mock 账本（`dev/tests/test_quota_guards.py` 里的 fake client）。
- 已知额度成本：eval/GET = 1；upload+featurespecs = 3；instantiate = 1（微版本已缓存）/ 2（冷缓存）；
  create_validation_part_studio = 1；validation pipeline = 13（含 render）/ 8（不含）；
  render = 1；is* 收敛探测每失败符号 +1；上传前必跑 `onshape_docs/scripts/fs_local_check.py`（0 调用）。
- 关键文件：`onshape_docs/scripts/fs_local_check.py`、`onshape_docs/scripts/live_symbol_sweep.py`（时间戳+增量落盘+
  断点续跑+自适应预算）、`onshape_rest_api_mode/{client,budget,operations}.py`、
  `onshape_docs/experience/{featurescript,rest-api}.md`、
  `onshape_docs/verification/live/{README,live-is-predicates,live-symbol-sweep}.json`。
- 验证结论（勿重复 live 验证）：`is*` 谓词集已在 3044 定案；跨版本 import 边界强证据
  为 3029 < 版本 ≤ 3044（静默拒绝）；spec 发射由 precondition 的 bound-spec +
  `annotation { "Name" }` 触发，与 body 无关。经验结论见 `onshape_docs/experience/`，证据见 `onshape_docs/verification/`。
