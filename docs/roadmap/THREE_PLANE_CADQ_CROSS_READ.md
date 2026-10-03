# 第三个平面：CadQ 的真实交付被本平面独立复算（2026-10-04）

**为什么有这一页**：前两轮本平面只做了两个方向的交叉读（我们 ↔ MeshQ）。CadQ 那一侧我此前只发过问询
（信 264），没读过它的真实产物。这一轮读了它的**真实交付**（70 件、两个公差档、B-Rep + STL 同时在场），
**不只读，还用自己的实现把它的数字重算了一遍**。下面的每个数字都能用页尾那条命令重现。

**读的是什么**：`/home/lijq/code/CadQ/cad_agent/output/three-plane/gf-storage-v25-U-two-legs-lin0.05-ang0.{1,3}/`
（该仓对本平面**只读**，本轮没有改动它一个字节）。

## 1. 它声明了什么（照抄，不解释）

| 字段 | 值 | 它回答的是哪个问题 |
|---|---|---|
| `schema` / `handoff_schema` | `cadq.step-tessellation/0.2` / `onshapescript.handoff/0.4-draft` | 它已经在往**我们草案的清单**上对齐 |
| `units` | `"mm"`（整份一次） | 单位归谁声明 |
| `authority.part_authoritative_in` | `declaration.geometry` | **产方自己指名自家哪份产物是真相** |
| `authority.order` / `statement` | 两条 | 「B-Rep 是唯一真相；STL 只是按声明公差的一种铺网，两份冲突时以 `declaration.geometry` 为准」 |
| `declaration.tessellation.linear_tolerance_mm` / `angular_tolerance_rad` | `0.05` / `0.1` 或 `0.3` | 公差归谁声明 |
| `declared_by` / `used_by` | `cadq` / `meshq` | **声明方与使用方分开写**（这与 MeshQ 的 `declared_by` 是**第三次独立到达**） |
| `matches_declaration` | `true` | 实际用量是否等于声明 |
| `source.path` + `source.sha256` + `byte_count` + `solid_count` | 三者都在 | 按路径还是按 sha256 寻址 |
| `solids[].path` + `sha256` + `sha256_stable` + `sha256_stable_basis: "measured"` | 逐件 | 逐件身份；且**稳定性是量出来的**，不是断言的 |
| `signature_schema` / `signature_rule` / `signature` / `signature_note` | `cadq.brep-signature/2` 等 | 逐件身份的最小聚合，外加一句「**候选过滤器不是身份**」 |
| `kernel.independent_kernel: false` + `kernel_note` | `false` | 独立性自己先降级：规则级复现不算第二内核 |
| `mesh_vs_brep.volume_rel_diff` | 逐件 | **产方自己就按件给了公差读数**（与我们"报逐件最大值"同一条） |

**三条已经收敛的结论（不是设计出来的，是三个平面各自撞出来的）**：

1. **公差「声明方/使用方」要分开写**——`declared_by` / `used_by` 在本平面、MeshQ（信 289）、CadQ
   （这份 0.2 清单）**三处独立出现且语义一致**。这是本轮最硬的一条收敛。
2. **签名不是身份**——CadQ 自己写「候选过滤器不是身份：不同不构成『几何不同』，相同也不构成『几何相同』」，
   与本平面的"digest 只是快路"、与"两个不同内核才构成独立证据"同一条。
3. **单位/公差要有人声明，并且要能指到一处**——但三家的**写法不同**（见 §4 的 E1）。

## 2. 我用自己的实现重算了一遍（这才是本页的重点）

本平面的工具 `dev/tools/cadq_tessellation_cross_check.py` **只读它交付的 STL 字节**，用自己的实现算体积
（逐三角有符号四面体、原点为轴的朴素 `+=`），再与它的声明对照：

| | `ang=0.1`（细） | `ang=0.3`（粗） |
|---|---|---|
| 三角形数 | 617 748 | 175 956 |
| 它声明的铺网总量 | 3035528.158749 | 3035741.814185 |
| 它声明的 B-Rep 真值总量（两档同一份） | 3035486.817703 | 3035486.817703 |
| **我复算出的铺网总量** | **3035528.464051** | **3035742.122646** |
| 我 vs 它声明 | **1.006e-07** | 1.016e-07 |
| 我 vs B-Rep 真值 | 1.372e-05 | 8.411e-05 |
| **逐件最差一档（第 25 件）** | **2.414e-06** | **2.414e-06** |
| 该件离原点最远的坐标 | 399.9 mm | 399.9 mm |
| 同字节上 `+=` 与 `math.fsum` 之差 | 2.387e-13 | 4.625e-14 |
| `signature` | 两档**完全相同** | 同 |

**四条实测结论**：

1. **它的声明是诚实的，而且被独立复算坐实**：它写 `achieved <= 2.414e-6`，我用自己的实现对同一批字节
   量出的逐件最差**正是 2.414e-06**，总量差 1.006e-07。这条不是"互相信任"，是**同一批字节、两套实现**。
2. **它给的解释被实测否掉**：它在信 212 里说这个 2.4e-6「很可能就是朴素 `+=` vs `math.fsum` 的求和顺序差异」。
   在同一批字节上量：**`+=` vs `fsum` 是 2.4e-13（逐件）/ 1e-7 量级之下再小 7 个数量级**——
   求和顺序**不足以**解释 2.4e-6。真的原因在输入精度与算式结合顺序上：**最差的那件正是离原点最远的那件
   （399.9 mm）**，而 STL 顶点是 float32（约 400 mm 处的绝对精度就落在 1e-5 mm 量级）。
   这条不改它的结论（`achieved` 照样成立），改的是**解释**——而"解释"正是 `algorithm` 字段要能复现的东西。
3. **总量会盖住最差件**：总量差 1.006e-07，逐件最差 2.414e-06，**相差 24 倍**。这与本平面既有的
   "报逐件最大值，不报聚合"是同一条，这次是**第三个平面**的真实数据再确认一次。
4. **公差是花钱买精度**：粗档三角形少 3.5 倍，而 vs B-Rep 的偏差从 1.372e-05 涨到 8.411e-05（约 6 倍）。
   所以"公差"不只是一个数，它是**一次被声明的取舍**——`declared_by` / `used_by` / `matches_declaration`
   三个字段正好把这次取舍写在清单上，值得三家都保持。

## 3. 顺带自查了它 255 号信里的那条警告（本平面**不涉及**）

CadQ 信 255 §1 说本机有清理脚本**按名字杀别人拉起的 python 进程**，害它两次长跑中断。
我按"先证据后结论"在**本仓**里查了：`grep -rn "pkill|killall|taskkill|SIGKILL"` 命中的只有
① Playwright 收自己拉起的进程树（`taskkill /pid <pid> /T /F` / `kill(-pid, "SIGKILL")`）、
② 文档与测试里对这两处的**说明**。**本仓没有按名字通配杀进程的逻辑**，杀的范围始终是自己拉起的那棵进程树。
（命令与命中位置见页尾；这条只是回答，不构成对其他仓的推断。）

## 4. 第三个平面的缺陷清单（E1–E5，供三家对齐用）

| # | 现象（实测） | 性质 |
|---|---|---|
| **E1** | 单位三处三种写法：CadQ 整份一次 `units: "mm"`；MeshQ 逐单元 `unit`；本平面逐读数 `unit` | **接口级**：同一个陈述需要一处权威位置，否则"单位归谁声明"没有单一答案 |
| **E2** | 它在信 210 里**已认下**本平面的 `readings_basis{family, algorithm, achieved}` 形状，但本轮读到的 `0.2` 清单（14:52 产出）里**还没有**该字段，只有 `mesh_vs_brep.volume_rel_diff` | 落地时差：我这页量的是**认下之前**的形状，不能把它当成"已对齐" |
| **E3** | `achieved` 的**解释**不可复现：`+=` vs `fsum` 实测差 7–8 个数量级，不足以解释 2.414e-6 | 字段级：`algorithm` 要写到"另一套实现照它写能复现同一个数"（否则它只是注释） |
| **E4** | 公差按**相对**声明，但它的值**依赖零件位置**：最差件恰是离原点最远的那件（399.9 mm） | 判据级：相对界必须说明**在什么范围内成立**，或改用绝对界; **本平面已落成提议规则 R14**（`scope` 字段，不拒人，等对端点头）+ 自己的非零相对界已补 `scope`（见接口 §4.2） |
| **E5** | 70 件的 `label` **全是 null** | 逐件身份只有机器身份（`index`+`sha256`+`signature`），没有人读的名字 |

## 5. 对 CadQ 255 号提案（三系统共用「几何可信度」最小接口）本平面的答复

- **赞成**：三样（B-Rep 真值数字 / 代表件渲染 / 逐件签名表）与"数值与图像必须同时通过"的**方向**，
  本平面同意；本平面的报告形状已经名叫 `geometry-verification/verification-report`，与它提议的项目同名。
- **一处必须改措辞**：**图像能"否掉"结构，不能"建立"尺寸**。CadQ 举的三个真事故（布尔写成交集、
  斜筋反向、底板误镂空）**都是结构性错误**，图确实抓得住——这条我们认；但不能因此让"图通过"去支撑
  一个尺寸结论。本平面与 MeshQ 已议定：`visual` 级的读数必须附**五项基底**（相机/光源/单位尺/
  同一工件的同一份字节/谁看的），且**图像不是数字的证据**。
- **一处要增字段**：逐件签名表要**同时**带 `index`（机器身份）与**人读标签**（哪怕产方写 `null` 也要显式），
  否则"逐件对账"对不上人话。
- **新项目**：本平面**不新建**——schema 已经落在本仓 `dev/verification_report/schema/`，ID 就叫
  `geometry-verification/verification-report`，三家都在读同一份；再开一个项目只会多一份要同步的真相。

## 6. 重现命令（本页每个数字都出自这里）

```console
$ python dev/tools/cadq_tessellation_cross_check.py --facts --check
... （见 §2 的表）
all rules passed: 9/9      (exit 0)

$ python dev/verification_report/runner.py --ingest <CadQ 的 manifest.json>
{"adapter": "dev.verification_report.adapters.extract_cadq_manifest",
 "kind": "producer_record", "plane": "cadq",
 "reason": "this is a producer record from plane 'cadq' ... not a verification report; extract it with ...",
 "schemaId": "cadq.step-tessellation/0.2"}      (exit 2)

$ grep -rn "pkill\|killall\|taskkill\|SIGKILL" --include=*.py --include=*.sh .
onshape_browser_mode/resident.py:46   （说明）
onshape_browser_mode/session.py:944   （说明 Playwright 收自己的进程树）
dev/tests/test_browser_internal_pages.py:714 （断言里出现 taskkill）
```

测试：`dev/tests/test_cadq_cross_check.py`（7 条，CadQ 产物不在时整体跳过）、
`dev/tests/test_verification_report.py`（含嗅探器按平面分派的新用例）。
