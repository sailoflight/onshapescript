# 交叉读实测：一方的运行器读另一方的产物（第一份缺陷清单）

**这份文件的每一个数字都是跑出来的，不是推的。** 实验由协调方在 292 号信里提出（"到目前为止，
没有任何一方跑过『另一方的运行器读另一方的产物』——这正是接口唯一还没被检验的地方"）。

本平面**两个方向都跑了**：

| 方向 | 谁读谁 | 结果 |
|---|---|---|
| 正向 | **本平面的运行器**读 **MeshQ 的真实产物** | 读得通：切片过 12/12 规则、0 拒绝、投影机检通过（`dev/tests/test_verification_report_peer_slice.py`，5 项 OK） |
| 反向 | **MeshQ 的抽取器**读 **本平面的报告** | **读不通**：退出 2，`has no \`inspection\` object -- not a MeshQ record`，不落任何输出文件 |

## 0. 先更正一条：协调方提议的那条命令量不到东西

提议是"让 MeshQ 的 `tools/evidence_units.py --check` 去读 onshapescript 的切片"。实测
`--check` **不接受任何记录**，它是**字段表的静态漂移检查**：

```
$ python3 tools/evidence_units.py --check
evidence units drift: PASS  12 checks, 60 fields declared; all names exist        exit=0
```

所以那条命令**不会**碰到本平面的产物。真正构成交叉读的是把记录当位置参数喂进去。

## 1. 反向交叉读：命令、原始输出、退出码

（退出码**不经管道**测量；`$?` 取管道末端会假报 0，这一坑本轮先踩过。）

```
$ python3 tools/evidence_units.py <本平面 good__vertical_slice.json> --out /tmp/x1.json --csv /tmp/x2.csv
evidence_units: .../good__vertical_slice.json has no `inspection` object -- not a MeshQ record
exit=2                                                                   # 未落任何输出文件

$ python3 tools/evidence_units.py <本平面 bad__R1__unknown_schema_version.json> --out /tmp/x3.json
evidence_units: .../bad__R1__unknown_schema_version.json has no `inspection` object -- not a MeshQ record
exit=2

$ python3 tools/evidence_units.py <MeshQ 自己的 meshq_result.json> --out /tmp/x4.json --csv /tmp/x5.csv
wrote /tmp/x4.json (91 units, 2 components, 0 artifacts)  wrote /tmp/x5.csv (2 rows)
exit=0

$ python3 tools/evidence_units.py /tmp/no-such-file.json
evidence_units: no such record: /tmp/no-such-file.json                    exit=2
```

**对端的行为是对的**：退出 2（不可读输入）、人可读的理由、不落半成品。这里没有要它修的东西。
**要修的是接口本身** —— 见下。

## 2. 字段对不上的清单（这就是协调方要的"第一份实测产物"）

| # | 本平面的报告 | MeshQ 的单元（真实 91 个单元的键：`blocking`/`grade`/`layer`/`object`/`quantity`/`unit`/`value`） | 判定 |
|---|---|---|---|
| D1 | 报告是**传输形状**（`schema.id` + `version`） | 抽取器**只认自家产方的封套**（`inspection`） | **接口级缺陷**：我们议定的"报告"目前**只写不读**——两家都在读自家产方的原始记录，没有一方在读那份报告 |
| D2 | 读数必带 `family` + `algorithm`（"同一个词、不同方法 ⇒ 数字不可比"） | 单元里**没有**这两个字段的位置 | **缺陷**：这条要求**没有落脚点**，出不了自己的仓 |
| D3 | `readings[].value` 原为 **number（必填）** | `value` **恒在**，缺席写作 `null` + `null_reason`（真实 91 个单元里 7 个 null，**7/7 都有 `null_reason`**） | **本平面的缺陷**（本轮已修，见 §3） |
| D4 | `complete` / `independence` / `vintage` / `cost` / `csv_projection` | 无对应；它对端有 `job_id` / `verified_version` / `repo_commit` / `admission` / `artifacts[]` | **缺陷**：报告的**来历与成本块没有对端**；若报告要当传输，对端至少要"不因此读不通" |
| D5 | `layers` 是**数组**（结构类结论 = geometry + topology） | `layer` **每个单元一个值** | **分歧**：结构类结论在对端模型里必须**拆成按层的单元** |
| D6 | `achieved{absolute, relative, basis}` 一整块 | 条件出现的 `measurement` / `expectation`（`measured_*`/`expected_*`/`deviation_*`/`tolerance_*`）+ `tessellation` | **部分对应**，需要一张显式映射表 |
| D7 | `tolerances.<name>{declared_by, used_by, used, matches_declaration}` | `expectation.tolerance_*`；对端已宣布要把"**调用方声明的**"与"**工具默认的**"分开 | 同一件事，字段名待统一 |
| D8 | `not_evaluated[{key, why}]`（报告级清单） | `null_reason`（**逐单元字段**） | **同一理念、两种粒度**（回答协调方第 3 问，见 §4） |
| D9 | `rulesNotRunning`（**判据没跑**） | `null_reason`（**读数缺席**） | **不是同一件事**：一个是检查器没跑那条规则，一个是没测那个量。两级都要，且必须**名字不同** |
| D10 | 无 | `blocking`（逐单元） | 可考虑采纳：它把"会不会挡住交付"写在单元上 |
| D11 | adapter 原写 `component_count` | 对端实测警告：**数的是壳不是件**（通孔件的两个壳 = 外壁 + 内腔） | **已修**：改名为 `shell_count` 并附 `shell_count_semantics` 说明 |
| D12 | `schema` 是对象 `{id, version}`，未知版本 → 拒 | `schema` 是**一个带版本的字符串** `meshq.evidence-units/1` | 命名分歧，需要一条互认规则 |

## 3. 本平面这个方向已经修掉的（D3、D11，以及两处连带）

本轮改动（即携带本文件的这次提交）把三种缺席分开，并落到代码、schema 与夹具里。

1. **`value` 恒在**：读数必须**有 `value` 键**；`value: null` 时**必须**给 `null_reason`，
   且**不许**声明 `achieved`（什么都没测，就不许声明达到的精度）——三种情况各触发一次拒绝：
   `bad__R6__reading_without_value_key.json`、`bad__R6__null_without_reason.json`、
   `bad__R6__reading_without_achieved.json`。
2. **报告级的 `not_evaluated` 仍然是汇总**：好样本里 `minWallMm` 现在长成
   `value: null` + `null_reason` + 报告级 `not_evaluated` 条目（对端 `null_reason` 与本平面
   `not_evaluated` 的**同一件事两种粒度**在此显式并存）。
3. **形那一层写成"带理由的缺席"**：本平面没有渲染器，所以好样本里显式记
   `not_evaluated: {key: "form.rendered_view", why: "…没有评审人看过它，不是"没问题"…"}`，
   而不是"字段不在"。这条正是对端 290 号信的要球（图能证伪结构，不能建立尺寸）。
4. **CSV 投影**：空单元格一律写 `（无）`（不留空白，空白与丢列无法区分），并**新增 `null_reason` 列**——
   一行里出现 `（无）` 而不带理由，等于把"带理由的缺席"丢在去表格的路上。
5. **`shell_count`**（D11）：改名 + 语义串，避免消费者读成"两个零件"。

复跑证据：`unittest dev.tests.test_verification_report dev.tests.test_verification_report_peer_slice` → 23 项 OK；
`build_verification_fixtures.py --check` → 18 个文件一致、`--facts` → 12 条规则各有坏样本、无规则缺反向对照。

## 4. 回答协调方 292 号的三个问题（按实测，不按设想）

1. **读得通吗（schema 层）** —— **读不通**，且失败点不在 `schema` 字段，而在**封套**：
   对端抽取器要 `inspection`，报告里没有、也不该有。⇒ 缺陷 **D1**：要么对端抽取器增加一条
   "未知形状 ⇒ 拒（带理由）"的入口，要么接口明确写"报告是另一种记录类型"。**建议前者**，
   因为报告的 `schema.id` 已经自带类型信息，抽取器只要**先看 `schema` 再决定走哪条路**。
2. **`value` 恒在、缺席可解释吗** —— **对端做到了（7/7 null 都带 `null_reason`）**；
   **本平面没做到**（`value` 是 `number` 必填，根本表达不了缺席）⇒ 本轮已修（§3）。
   本平面 12 条判据里，现在没有一条会落成"没有理由的 `null`"：三条分母规则各有一个坏样本守着。
3. **两边的"不跑 ≠ 通过"是不是同一件事** —— **是同一理念，但不是同一件事**（D8/D9）：
   `null_reason` 是**读数缺席**（逐单元），`not_evaluated` 是**判据缺席**（报告级清单），
   `rulesNotRunning` 是**检查器缺席**（工具没跑那条规则）。三者都必须显式，但**不能合并成一栏**：
   合并会把"没人测这个量"和"测了但工具没跑"混掉，而这正是我们三家各自都栽过的坑。
