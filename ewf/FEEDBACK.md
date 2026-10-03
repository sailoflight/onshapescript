# onshapescript EWF 回灌清单

通道：`docs/project-onboarding.md` §3。下面这张表的列名逐字固定，机器靠它认出队列。
`状态` 列只有 EWF 侧能改；项目侧只追加新行。（本文件 15 行已于 2026-10-02 全部落定，见文末〈处置记录〉。）

叙事版在 [`README.md`](README.md) §11（**id 集合与下表逐条一致**）。

| id | 类型 | 事实（含原始证据） | 建议去向 | 状态 |
|---|---|---|---|---|
| onshapescript-FB-01 | 文档 | `docs/project-onboarding.md` §1 写「`<project>/ewf/` 只放 `instance.yaml` + `README.md`（+ `FEEDBACK.md`），不放代码」；而 `docs/abi-users.md` §6 的通用邀请要求「写个小脚本，从你们的发布数据生成它」。两处都没有说清「生成器住在哪里」。本次的落点是项目自己的工具目录 `dev/tools/build_ewf_instance.py`（`instance.yaml` 由它生成，`--check` 可复跑），`ewf/` 保持三份交付物。复现：`ls /home/lijq/code/onshapescript/ewf` 只有 `instance.yaml`、`README.md`、`FEEDBACK.md`。 | `docs/project-onboarding.md` §1 补一句写方向生成器的约定位置（`abi-users.md` §6 只说了「写一份 instance.yaml，或者写个小脚本生成它」） | 无需改规范 |
| onshapescript-FB-02 | OQ | `ewf-instance.schema.json` 的 `instance.open_questions` items pattern 是 `^OQ-\d{3}$`。写这份实例时撞到 4 个项目自有待定项（上游许可边界、产物留存、发行说明保留集合、是否跟随 spec 0.6.1），没有任何机器可读位置，只能进 `instance.note.text` 与 `FEEDBACK.md`。 | OQ-016 | 已登记 |
| onshapescript-FB-03 | OQ | `ewf-instance.schema.json#$defs/instance` 的 properties 里没有 provenance / source 字段（只有 Entity 有 `provenance`）。生成器读三份源数据（归档 + `.sha256` 边车、`dev/tools/consumer_release_spec.py`、`onshape_docs/verification/resident-login-survival-2026-09-26.json`）并复算后才写出实例，但实例里没有地方记录「源是什么、摘要是什么、是否过期」；`generate_instance.py --check` 只能是仓库外的手工补偿。 | OQ-011 | 已登记 |
| onshapescript-FB-04 | 条款 | `ewf-instance.schema.json#$defs/artifact.identity` 是单个 string。本产物的真实身份是三元组：server 版本 `1.3.0` + 来源 revision `6ceacfb` + 归档 sha256 `d112de9c63dd…`，另有一份 399 行的逐文件摘要清单。`instance.yaml` 只能把 sha256 放进 `identity`、revision 放进 `baseline.configuration` 的 `software-commit`、版本放进散文，机器无法从任一处推出另外两处。 | OQ-023 | 已登记 |
| onshapescript-FB-05 | 条款 | `ewf-instance.schema.json` 的 `$defs/release` payload 只有 `released_baseline` / `package` / `release_gate` / `transition_work_node` / `target_environment`，**没有** `supersedes`；而 `$defs/baseline` **有** `supersedes`。发布链真实发生过三次重发（`resident-login-survival-2026-09-26.json` 的 `released_681a4cd` / `released_e667bcc` / `released_31d2b9c`），取代关系只能借 baseline 表达。 | OQ-020 | 已登记 |
| onshapescript-FB-06 | 条款 | 验证记录点名 6 个构建 revision（`c10a235` / `1f9f7c2` / `681a4cd` / `e667bcc` / `31d2b9c` / `6ceacfb`），而 `ls /home/lijq/code/onshapescript-releases/*.zip` 只有 2 个 zip；其余只剩摘要与字节数。EWF 里没有「留存政策」的字段或 Entity 类别（Release payload、Gate criterion、Entity 类别里都没有「留多久 / 谁负责 / 何时可以删」这类落点）。本行初稿把「可得性」也算作缺口，EWF 侧复现后**推翻**了那一半：`existence` 的 `engineering_object: absent` + `record: persistent` 就能表达「字节不在、记录在」；真正缺的只有留存政策（见文末处置记录的更正三）。 | 建议新建 OQ（产物留存与处置） | 已登记 |
| onshapescript-FB-07 | 条款 | `common.schema.json#$defs/externalRef.system` 的 enum 是 `zentao / git / onshape / plm / ci / issue-tracker / document-system / requirements-tool / custom`，没有「发布 / 分发渠道」。GitHub Release 只能写成 `custom` + `system_name: github-releases`，而 `system_name` 不在 required（required 是 `system` / `external_id` / `role`），于是「custom 必须自报名字」无人可查。 | 建议新建 OQ（外部分发渠道是否要一等取值） | 已登记 |
| onshapescript-FB-08 | 条款 | 产物白名单里确实包含随归档再分发的上游材料（本地 FeatureScript 语料、Onshape 原生文档副本、内置 wheel）。但 `$defs/artifact` payload 只有 `realization_kind` / `satisfies` / `identity`；`governance_drivers` 里的 `regulatory-formality` 只是驱动因素名、不带任何载荷；也没有 license / notice / third-party 类 Entity。许可义务只能写进散文。 | 建议新建 OQ（许可与第三方再分发是否需要一等表达） | 已登记 |
| onshapescript-FB-09 | 工具 | 接入协议要求在两条验收命令里「先 `--help` 确认参数名」，但官方校验器不认这个选项：`cd /home/lijq/code/ewf && ./.venv/bin/python tests/validate_examples.py --help` → `未知选项：--help` + 用法，退出码 **1**。参数名只能从别处（`ewf_tools.check -h` 或源码）确认。 | `tests/validate_examples.py` 加 `-h/--help` | 已修复（工具侧） |
| onshapescript-FB-10 | 非缺口 | `consumer_release_spec.py --check` 写出的 `release-manifest.json` 是 `artifactStatus: spec-only` / `artifactFormat: null`（产物尚未构建）。看着像「EWF 无法表达未构建的产物」，实测 `existence.engineering_object: absent` + 一份计划的摘要清单可以是两个不同的 Artifact / Record，现有条款足够解释。 | 已由现有条款解释（本实例不据此改任何条款） | 已由现有条款解释 |
| onshapescript-FB-11 | 非缺口 | `common.schema.json#$defs/id` 的 pattern `^[A-Za-z0-9][A-Za-z0-9._:/#-]*$` 不允许空格，真实命令 `gh release create` / `sha256sum -c` 只能改写成工具标识 `gh-release` / `sha256sum`。原始报错：`instance/entities/10/verification_evidence/method :: 'gh release download + sha256sum -c' does not match '^[A-Za-z0-9][A-Za-z0-9._:/#-]*$'`。改写后真实命令有落点：`executionNode.note.text` 与 `provenance.note`（`provenance.note` 是纯 string），本实例就写在两处。 | 无需改规范（`note.text` 就是真实命令的落点） | 无需改规范 |
| onshapescript-FB-12 | 文档 | `common.schema.json#$defs/governanceDriver` 只有 16 个枚举值。写实例时想说明「为什么 `cost-of-failure` / `rollback-need` / `regulatory-formality` 对本实例成立」，schema 与 SPEC 都没有承载处，只能写进 `tailoring.note` 或实例 note。 | OQ-017 | 已登记 |
| onshapescript-FB-13 | 工具 | 同一个 schema 目录里同时存在两个 spec 版本时，两个独立实现结论相反（判等性问题）。原始证据（观察时点：2026-10-02，EWF 仓 `0.6.0` → `0.6.1` 升级进行中）：EWF 工作树里 `schema/common.schema.json`、`vocabulary.stage.json`、`vocabulary.tailoring.json`、`vocabulary.work-node.json` 的 `x-ewf-spec-version` 已是 `0.6.1`，而 `ewf-benchmark.schema.json`、`ewf-core-model.schema.json`、`ewf-execution.schema.json`、`ewf-instance.schema.json` 仍是 `0.6.0`。此时官方校验器照跑并 PASS（表头 `EWF Core V0 example validation —— spec_version 0.6.1`），消费者工具拒绝运行：`RuntimeError: 无法从 EWF schema 读出唯一 spec_version：['0.6.0', '0.6.1']`（`ewf_tools/loader.py:127`）。同一份实例、同一份 schema 目录，一个 PASS、一个连跑都不跑。升级窗口关闭后（8 个 schema 文件全为 `0.6.1`）两者重新都 PASS，消费者工具对 spec 版本漂移只记一条说明、不影响判定。 | 建议新建 OQ（版本混合期该 fail-fast 还是取新） | 已登记 |
| onshapescript-FB-14 | 工具 | `[files]` 层失败会短路 schema 层，schema 错误一条都不打印。复现（合成实例，与本项目实例无关）：先不放 `README.md` → 官方校验器只输出 `FAIL —— 1 条问题：- <proj> [files] 缺少必需文件 README.md`；补上 `README.md` 后再跑同一条命令 → `FAIL —— 2 条问题：- [schema] instance.yaml 未通过 schema 校验（6 条）` 并列出 6 条明细。只按第一次输出修的人，第一步完全看不到 schema 错误。两个实现里 `ewf-tools check` 会在输出里明说「断言：未校验」，官方校验器对 schema 层没有任何「未求值」提示。 | 建议官方校验器在 files 层失败时仍打印 schema 层，或明说该层未求值 | 已由现有条款解释 |
| onshapescript-FB-15 | 文档 | 实体通用字段（`statement` / `title`）定义在 `$defs/entityInstance` 上，而 kind 专用子对象是 `additionalProperties: false`；写错层时官方报错指向「字段名不合法」。原始报错：`instance/entities/11/verification_case :: 'statement' does not match any of the regexes: '^x-'`、`instance/entities/6/baseline/configuration/0 :: 'value' does not match any of the regexes: '^x-'`，同一路径另有 `'identity' is a required property`。报错本身正确，但读者会去改字段名，而不是把它移出 kind 子对象。 | 建议在 `examples/` 或 `docs/project-onboarding.md` §2 给一个最小 `verification_case` 与 `baseline.configuration` 示例 | 无需改规范 |

补充：本文件只声明 `onshapescript-FB-NN` 命名空间下的项目自有编号；不引用任何未登记的 `OQ-\d{3}`
（`OQ-011` / `OQ-016` / `OQ-017` / `OQ-020` / `OQ-023` 均为 EWF 侧已登记编号，只出现在「建议去向」列）。

上表原始输出的取得方式：官方校验器 `cd /home/lijq/code/ewf && ./.venv/bin/python tests/validate_examples.py --project /home/lijq/code/onshapescript/ewf`；消费者工具 `cd /home/lijq/code/ewf-tools && ./.venv/bin/python -m ewf_tools.check --project /home/lijq/code/onshapescript/ewf`；schema 直读引用 `/home/lijq/code/ewf/schema/*.json` 的具体路径与键名，可逐字复核。

---

## 处置记录

### 2026-10-02 · EWF 侧对 15 行的判定：全部落定（`待处理` → 0 条）

**判定方式**：EWF 侧对每一行都做过一次**就地复现**（不是照抄本文的数字），产物与全部原始输出在
`/home/lijq/code/ewf-tools/verification/bundles/fb-triage/`（`bash run_all.sh` 一键复算；`REPORT.md` 逐条给了命令、退出码与逐字反例）。
复现的义务按 `docs/project-onboarding.md` §3 兑现：**先复现，再登记**。下表是结论，
下面三段是**必须写清的四件事**（三处更正 + 一处明确拒绝）。

| 行 | 判定 | 一句话依据 |
|---|---|---|
| `FB-01` | `无需改规范` | 「生成器住哪里」在 `docs/abi-users.md` §5.10 已点名该项目路径，只有 §1 的目录约定没提；补文档可选，不是缺口。 |
| `FB-02` | `已登记`（`OQ-016`） | instance-local 待定项确实只能借 `^OQ-\d{3}$`；**顺带更正**：`note.text` 自述「4 条」而行里是 3 条。 |
| `FB-03` | `已登记`（`OQ-011`） | 23 个 instance 属性里确无 `provenance` / `source` / `origin`，与 `OQ-011` 同一问题。 |
| `FB-04` | `已登记`（**新 OQ-031**） | `artifact.identity` 是单 string（本机逐字复核：payload 只有 3 个键）；`OQ-023` 管「多处声明谁权威」，**接错地盘**。 |
| `FB-05` | `已登记`（`OQ-020`） | `release` 5 键无 `supersedes`、`baseline` 有，属实；并已在 `OQ-020` 的**证据**里补上这条实测（release 5 键无 `supersedes`、3 次重发）；affects 已覆盖 `schema/ewf-instance.schema.json`。 |
| `FB-06` | `已登记`（**新 OQ-032**） | 「6 个 revision / 2 个 zip」属实；但「可得性没有落点」**被反例推翻**（`existence` 能表达），真正缺的是留存政策。 |
| `FB-07` | `已登记`（`OQ-012`） | `externalRef.system` 无发布渠道取值属实；`OQ-012` 的 summary 与候选**已逐字覆盖**，不另建 OQ。 |
| `FB-08` | `已登记`（**新 OQ-033**） | artifact 3 键、9 个 kind 无许可类、`regulatory-formality` 只是驱动因素名——逐条复核成立。 |
| `FB-09` | `已修复（工具侧）` | 见下「更正一」。 |
| `FB-10` | `已由现有条款解释` | 「未构建的产物」今天就能表达：`existence: {engineering_object: absent, record: persistent}` 的合成实例官方 **rc 0**；现场 `--emit` 也确认 `artifactStatus: spec-only`。 |
| `FB-11` | `无需改规范` | 空格 id 确实不合 `^[A-Za-z0-9][A-Za-z0-9._:/#-]*$`；改写为工具标识是正确落法，规范无需动。 |
| `FB-12` | `已登记`（`OQ-017`） | `governanceDriver` 16 个取值确实只是名字、无载荷，与 `OQ-017` 同一问题。 |
| `FB-13` | `已登记`（`OQ-030`，**2026-10-02 新建**） | 见下「更正二」。 |
| `FB-14` | `已由现有条款解释`（**且明确拒绝行里的建议**） | 见下「拒绝」段。 |
| `FB-15` | `无需改规范` | 三条报错逐字复现（含 `'statement' does not match any of the regexes: '^x-'`）；这是**诊断措辞**问题，不是模型问题。 |

**更正一（`FB-09`）**：「`-h` 被静默当筛选名」这条**已修**，而且顺手把一个更宽的口子堵上：旧实现只拦
`arg.startswith("--")`，所以**任何**单横线选项都会掉进用例名筛选器。现在 `-h` / `--help` 都打印用法
并返回 **0**，任何单横线未知选项都与双横线一样被拒（回归两条：`test_help_flags_print_the_usage_and_exit_zero`、
`test_single_dash_unknown_option_is_not_taken_as_a_case_name`）。
**同时更正行里的一个前提**：「协议要求先 `--help`」不成立——`docs/project-onboarding.md` 全文
`--help` **0 命中**。所以这条不是「违反了协议」，而是「一次求助被读成一条『仓库坏了』的结论」，
按后者修。

**更正二（`FB-13`）**：行里的机制、退出码、相反结论**全部复现**，本机另外重做了一遍——
把 `schema/*.json` 里 4 个文件的 `x-ewf-spec-version` 改成 `0.6.0`（其余保持 `0.6.1`）：
官方校验器 **rc 0 / PASS**（它的版本表头是 `tests/ewfkit/schema.py` 里的**手写常量**，根本不读文件），
消费者 `ewf_tools.check` **rc 1** 抛 `RuntimeError: 无法从 EWF schema 读出唯一 spec_version：['0.6.0', '0.6.1']`
——**没有任何层标**，而 `EWF-VER-004` 要求每次失败都归到六层之一。已登记为 **`OQ-030`**
（混合版本目录是 fail-fast 还是取新、谁负责检查）。你们还实测出「仓内守卫判 2 failed 但两个 CLI 都不跑它」，
这一条也写进了证据——**今天没有任何用户可达的路径**会报出混合版本，这是 `OQ-030` 存在的直接理由。

**更正三（`FB-06` 的一半）**：「可得性没有落点」**不成立**，这是本轮复现**推翻**的一处。
`EWF-ENT-001` 逐字规定「Object exists ≠ Managed Engineering Object ≠ Persistent Engineering Record」三者
MUST 可分离表达，`existence` 的 `engineering_object: absent` + `record: persistent` 就是「字节不在、记录在」；
合成实例官方 **rc 0**。你们真正缺的那一半——「保留多久 / 谁负责 / 何时可以删」——**成立**，已建 `OQ-032`。
**把两半分清很重要**：否则下一个人会以为「只要用 `existence` 就够了」。

**拒绝（`FB-14` 的前半句）**：行里建议「`[files]` 层失败时仍打印 `schema` 层明细」——**不按它做**，
而且这是 15 条里唯一一条 EWF 明确说「不要照建议改」的。理由是条款 MUST，不是风格偏好：
`SPEC.md` §20 逐字写「前一层不通过时 MUST 停止推进到后一层（层级顺序即失败优先级）」，
`EWF-VER-004` 的整条价值就是「两个实现都判失败时，能说清它们失败在**同一件事**上」。
在 files 层失败后继续求值 schema 层，会让「层标」变成「我跑了哪些层的流水账」，
两实现的层序不再可比。你们观察到的现象是真的（只报 1 条 `[files]`，补上 `README.md` 后才有 3 条
`[schema]`），但**它是条款要求的短路**，不是缺陷。其余部分判 `已由现有条款解释`。

**本轮之后本项目的队列**：`待处理` **0 条**（15 行全部有状态）。`ewf/instance.yaml` 我方未改动。

**引用的 OQ 现在都真实存在**：`OQ-011` / `OQ-016` / `OQ-017` / `OQ-020` / `OQ-023` 之外，
本轮新增了 `OQ-030`（`FB-13`）、`OQ-031`（`FB-04`）、`OQ-032`（`FB-06`）、`OQ-033`（`FB-08`），
四条都已进 `docs/open-questions.md` 与 `SPEC.md` §24。
