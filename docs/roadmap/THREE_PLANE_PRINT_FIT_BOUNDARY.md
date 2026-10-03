# 打印适配的边界：谁判定可打性、行程与摆放声明在哪注入（2026-10-04 实测版）

**这一页回答目标②**。结论先说：**可打性不是任何一个建模平面能判定的**——它是一次
"读数 vs **被声明的机器包络**"的比较，而**包络是消费方的状态**，所以三个平面都只允许出**读数**，
谁都不能盖"可打印"这个章。下面每条都有命令与原始输出。

## 1. 本平面的答案（已经在代码里，不是新写的立场）

`fdm_analysis/conversion/print_basis.py` 用两条规则把这件事挡住（规则本身可跑，见 §5）：

```python
envelope = block.get("envelope") or {}
owner = envelope.get("declared_by")
if owner not in (None, "consumer"):
    refusals.append(_refusal(
        3, "declaration.print.envelope", f"the envelope is declared by {owner!r}",
        "an envelope is machine state: only the consumer declares it, and no producer stamps a "
        "printability verdict"))
verdict = block.get("printable")
if verdict is not None:
    refusals.append(_refusal(
        3, "declaration.print.printable", "the producer stamped a printability verdict",
        "return the readings and let the consumer compare them against its own envelope"))
```

而清单里发出去的是**显式缺席**（`fdm_analysis/conversion/step_tessellation.py`）：

```
"envelope": {"declared_by": "consumer", "source": None, "x_mm": None, "y_mm": None, "z_mm": None},
"envelope_note": "machine state, not geometry: a printability verdict is a consumer-local
                  comparison against a declared envelope, and no producer may stamp one",
"min_wall": {"value_mm": None, "grade": "unknown", "reason": "no thickness analyzer is installed on this host"},
```

三样东西都在：**谁声明（consumer）**、**值是空（null，不是 0）**、**为什么空（说明）**。
可打性本身被列进 `evidence_grades.visual`（"is the part printable on a given machine (needs a declared envelope)"），
与 MeshQ 的 `grade_tiers.visual` 是同一处理——**不可离线判定的东西必须落在视觉/待评审那一档**。

## 2. 另外两个平面**实测**有什么（这才是这一页的活）

工具：`dev/tools/print_fit_cross_read.py`（只读，离线，不写对方任何文件）。

| 问题 | 实测 | 判定 |
|---|---|---|
| 有产方给机器状态盖章吗（envelope/bed/travel/placement/printer/machine/printable）| 扫了 **400 个 JSON**（MeshQ `artifacts/` + CadQ `print-adaptation/`）→ **0 命中** | ✅ 边界在实践里成立：没人盖章 |
| 打印判定的**输入**跟判定一起走吗 | CadQ 悬垂表 **340 行 / 70 件**，列 `part,face,geom,area_mm2,z_mm,normal_z,worst_drop_mm,needs_support`；**没有一行缺输入** | ✅ |
| 判定能由**发出来的列**重算吗 | **不能**：`worst_drop_mm = 4.0` 同时出现在 `True` 与 `False` 两种判定里；且 `1.5 → True` 而 `1.747 / 2.328 / 3.058 / 10.1 / 11.2 / 114.55 → False` | ❌ **缺陷 E6** |
| 声明出来的配合目标**有主人**吗 | `fit-gap-r17.json` / `fit-gap-all-r22.json`：`target_mm = 0.15`，行结构 `part/gap_before/gap_after/action`，**没有任何 owner 字段** | ❌ **缺陷 E7** |
| 对端怎么给「最小壁厚」 | **实测修正（2026-10-04 晚）**：在其 `contract-slice/work_slice_clean/meshq_result.json` 里 `wall_thickness` 是 `grade: "heuristic"` + `method: "ray-cast along -normal from face centres"` + `samples 72 / hits 72` + `min_mm 4.0` + `p05 4.0 / median 8.5022 / max 17.1302` + `caveat: unreliable at bevels, embossed text and sliver faces` + `blocking: false` —— **不是 `unknown`**：上一轮我按来信记成 unknown 是**错的**，此处更正（`minWall` 字段名对不上，它在别处的另一支探针里才是 unknown）。 | ⚠️ 逐单元 `value` 缺 `unit` 归属，且与本平面的 `min_wall: unknown` **并不一致**——这正是要跟对端对的点 |

## 3. 因此②的接口结论（三条）

1. **谁判定可打性**：**消费方**（机器/材料/工艺的持有者），依据是产方给的**读数** +
   自己声明的**包络**。产方只许出读数与它自己判据的**输入**，不许出"可打印"这个结论。
   实测依据：两个对端的记录里**没有任何产方盖的机器状态章**（400 个 JSON，0 命中）。
2. **行程与摆放声明注入在哪**：注入在**消费方的机器档案**里，作为**显式缺席**出现在产方清单中
   （`declared_by: "consumer"` + `x/y/z: null` + `envelope_note` 说明为什么）。
   本轮的 grep 也证明另外两个平面**既不声明也不假设**它——所以这里没有"三家各写一份"的风险，
   只有"谁持有机器"这一个答案。
3. **判定必须带判据**：能重算才叫证据。**E6 就是这条的反例**：CadQ 的悬垂判定带了输入，
   但**判据本身没跟出来**（同一个 `worst_drop_mm` 给出两个答案），所以消费者**无法复核**，
   只能选择相信或不相信。这与三家已经议定的"判决要带读数、判据、判据主人"是同一条，
   只是这次发生在**打印适配**这条腿上。

## 4. 两条要跟 CadQ 对的（E6 / E7）

* **E6**：悬垂表要么补上真正决定 `needs_support` 的量（例如每个面的悬垂角度、判定用的阈值、
  或"该值来自哪个三角形/法线"），要么把 `needs_support` 撤掉只留读数。
  **判据可以只说来源**（"阈值 45°、按面色 vs 竖直"），但必须能让人重算。
* **E7**：`target_mm = 0.15`（配合间隙）是**打印/装配的取舍**，请给 `declared_by` / `used_by`，
  与三家已经在公差上收敛的那对字段一致（产方声明、消费方复用、清单写明）。

## 5. 重现命令（本页每个数字都出自这里）

```console
$ python dev/tools/print_fit_cross_read.py --facts --check
CadQ overhang table: 340 rows / 70 parts, columns ['part','face','geom','area_mm2','z_mm','normal_z','worst_drop_mm','needs_support']
  judgements: ['False', 'True'] | rows missing an input: 0
  same shipped input, two judgements: {4.0: ['False', 'True']}
  owner column: False
CadQ fit-gap-r17.json: target_mm=0.15 columns=['action','face_x','gap_after','gap_before','part'] owner=False
CadQ fit-gap-all-r22.json: target_mm=0.15 columns=['action','axis','gap_after','gap_before','panel','part'] owner=False
declaration scan: {'files_scanned': 400, 'hits': []}
this plane's contract: {'refuses_a_producer_envelope': True, 'refuses_a_producer_printability_verdict': True}
PASS cadq-overhang-judgement-carries-its-inputs
FAIL cadq-overhang-judgement-recomputable-from-shipped-columns
FAIL cadq-fit-gap-target-has-an-owner
PASS no-plane-stamps-a-machine-state
PASS this-planes-contract-refuses-to-stamp-either
3/5 rules passed -- the gaps above are measured interface defects      (exit 1)
```

**exit 1 是刻意的**：这个工具量的是**接口缺陷**，两条失败规则就是 E6/E7；等 CadQ 补上字段，
同一条 `--check` 会变成 5/5。测试 `dev/tests/test_print_fit_cross_read.py`（8 条）把这**两个方向**
都钉住：既断言当前的两条失败**确实存在**，也断言本平面自己的契约**拒绝**产方声明的包络与产方盖的可打性章。
