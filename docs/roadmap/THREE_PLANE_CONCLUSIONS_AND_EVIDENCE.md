# 三方协商：结论与证据一页对账（2026-10-04）

**这一页把目标的每一项结论对到它的证据**（命令 / 原始输出 / 提交 / 文件路径 / 收据号），
使"做过什么"可以在一个地方核对，而不必翻会话记录。

## ① 几何导入导出边界

| 子问题 | 结论 | 证据 |
|---|---|---|
| 谁转谁 | 逐件身份与读数由**生产方**声明，消费方只做比较；**判决不随读数旅行**（裸判决字段一律拒，维持 R9，门槛是三元素 `{reading, criterion, owner}`） | `docs/roadmap/THREE_PLANE_VERIFICATION_INTERFACE_V1.md`（v1.3 定案 ④⑤）；台账 3.8 / 4.19；提交 `d3bc640` |
| 单位与公差归谁声明 | 单位逐数字声明；公差带 `declared_by`/`used_by` 两个名字；**相对界必须说明适用范围**（E4 → 规则 R14） | 接口 §4.2；`dev/verification_report/rules.py`；提交 `13d9958` |
| 逐件身份 | 三家都给**内容摘要**，且都声明稳定性依据；名字必须**显式**（`label: null` 也算） | `docs/roadmap/THREE_PLANE_PER_PIECE_IDENTITY.md`；`dev/tools/per_piece_identity_cross_read.py` |
| 按路径还是 sha256 寻址 | **摘要寻址，路径最多是提示**；摘要只是**过滤器不是身份**（CadQ 的 `signature_note` 原文被收下） | 同上；`THREE_PLANE_CADQ_CROSS_READ.md`；提交 `23788a9` / `fd888d6` |

**对 CadQ 真实交付的独立重算（本平面自己的实现）**：

```
PASS aggregate-within-declared [gf-storage-v25-U-two-legs-lin0.05-ang0.1]: measured vs declared aggregate 1.006e-07 <= 2.414e-06
PASS worst-part-within-declared [gf-storage-v25-U-two-legs-lin0.05-ang0.1]: worst part #25 2.414e-06 (farthest coordinate 399.9 mm)
PASS declared-bound-is-not-explained-by-summation-order [gf-storage-v25-U-two-legs-lin0.05-ang0.1]: += vs fsum 2.387e-13 <= 1e-12, i.e. 1e+07x smaller than the residual
PASS per-piece-not-aggregate [gf-storage-v25-U-two-legs-lin0.05-ang0.1]: worst part 2.414e-06 is 24.0x the aggregate 1.006e-07
PASS aggregate-within-declared [gf-storage-v25-U-two-legs-lin0.05-ang0.3]: measured vs declared aggregate 1.016e-07 <= 2.414e-06
PASS worst-part-within-declared [gf-storage-v25-U-two-legs-lin0.05-ang0.3]: worst part #25 2.414e-06 (farthest coordinate 399.9 mm)
PASS declared-bound-is-not-explained-by-summation-order [gf-storage-v25-U-two-legs-lin0.05-ang0.3]: += vs fsum 4.625e-14 <= 1e-12, i.e. 5e+07x smaller than the residual
PASS per-piece-not-aggregate [gf-storage-v25-U-two-legs-lin0.05-ang0.3]: worst part 2.414e-06 is 23.8x the aggregate 1.016e-07
PASS signature-is-tolerance-independent [both variants]: 2 tolerance variants, one signature=True, triangle counts [175956, 617748]
all rules passed: 9/9
exit=0
```

**逐件寻址实测**：

```
PASS every-piece-is-reachable-from-a-content-digest: this plane: per-part digest; CadQ: 70/70 solids carry one; MeshQ: 1 digest(s) in `outputs[]` covering [['block']]
PASS the-digest-declares-whether-it-is-stable: this plane: `sha256_stable` + the digest recorded twice as evidence; CadQ: ['True'] (basis ['measured']); MeshQ: [True]
FAIL a-piece-names-its-label-or-says-null-explicitly: this plane: `label: null` (an explicit absence); CadQ: 70/70 carry the field, 70 of them null; MeshQ: no `label`/`name` field at all -- a piece's only human-facing name is its object key ['block'], so it has to be inferred from a dict key
PASS no-piece-is-addressed-by-a-path-alone: this plane reduces the path to a file name; MeshQ publishes an ABSOLUTE path (['/home/lijq/code/MeshQ/artifacts/contract-slice/work_slice_clean/block_hole.stl']) beside its digest, so the digest must be the address
FAIL the-record-states-which-address-is-authoritative: CadQ: ['signature_note: 候选过滤器不是身份：不同不构成『几何不同』，相同也不构成『几何相同』；判决在声明的等价容差下做。']; MeshQ: none
3/5 rules passed
exit=1
```

## ② 打印适配的分工与接口

| 子问题 | 结论 | 证据 |
|---|---|---|
| 谁判定可打性 | **消费方**（机器/材料/工艺持有者）用"读数 vs 被声明的机器包络"判定；产方**不许**盖"可打印"章 | `docs/roadmap/THREE_PLANE_PRINT_FIT_BOUNDARY.md` §1（含本平面两条拒绝规则的原文） |
| 行程与摆放声明在哪注入 | 注入在**消费方的机器档案**，在产方清单里表现为**显式缺席**（`declared_by: consumer` + `x/y/z: null` + 说明） | 同上；`fdm_analysis/conversion/step_tessellation.py` 的 `envelope`/`envelope_note` |
| 实测（两个对端） | 扫 400 个 JSON → **0 个产方盖的机器状态章**；CadQ 悬垂表 340 行输入齐全但**判据没跟出来**（E6）；`target_mm` 无主人（E7） | 下方原始输出；提交 `abaa5d9` |

```
PASS cadq-overhang-judgement-carries-its-inputs: 340 rows over 70 parts, columns ['part', 'face', 'geom', 'area_mm2', 'z_mm', 'normal_z', 'worst_drop_mm', 'needs_support']; rows missing an input: 0
FAIL cadq-overhang-judgement-recomputable-from-shipped-columns: same shipped input, two different judgements: {4.0: ['False', 'True']}
FAIL cadq-fit-gap-target-has-an-owner: fit-gap-r17.json: target_mm=0.15 owner=False; fit-gap-all-r22.json: target_mm=0.15 owner=False
PASS no-plane-stamps-a-machine-state: scanned 400 JSON files under the peer trees; stamps found: none
PASS this-planes-contract-refuses-to-stamp-either: {"refuses_a_producer_envelope": true, "refuses_a_producer_printability_verdict": true}
3/5 rules passed -- the gaps above are measured interface defects
exit=1
```

## ③ 上层封装的共享契约草案

| 子问题 | 结论 | 证据 |
|---|---|---|
| 字段 | 交接 schema `onshapescript.handoff/0.4-draft`：逐件摘要 + 稳定性依据 + 逐数字单位 + `achieved{absolute,relative,scope,basis}` + 面积/体积/包围盒 + 三级缺席 + `evidence_grades` | `docs/roadmap/THREE_PLANE_HANDOFF_SCHEMA_DRAFT.md`；`fdm_analysis/conversion/step_tessellation.py` |
| schema 归属 | schema id 由**发布方**拥有（本平面 `onshapescript.*`，CadQ `cadq.step-tessellation/0.2`，MeshQ `meshq.evidence-units/1`）；不做跨平面改名 | `THREE_PLANE_CADQ_CROSS_READ.md` §1；`CROSS_WALK.md` |
| 是否需要路由器 | **v1 不需要**：一家一个运行器，适配器只抽字段；运行器按 `schema` 分派，认不出就点名 adapter 并退 2 | `dev/verification_report/runner.py`（`sniff_schema` + `--ingest`）；提交 `20a7351` |

## ④ 加强建模合作的具体做法

九条做法（读产物不读信 / 确认后还要自己复现 / 未确认规则不伤人 / 会自己关掉的检查 / 先修自己 /
证据分级并公开更正 / 一个运行器是唯一权威 / 点名引用对方的好做法 / 结论落仓 + 台账 + 收据）：
`docs/roadmap/THREE_PLANE_COOPERATION_PRACTICES.md`（提交 `45601df`，台账 3.16），
末尾附**第四个平面接入最小清单**。

## 第一个实现缺口：Onshape 侧没有导入能力 → **已实现且真机确认**

- **真机状态**（记录原文）：`live-confirmed: entry route, file input, submit control, digest addressing, and
  (after three code fixes found by live runs) the landing judges`；第三次确认运行落成一个真实 24 位十六进制元素
  `7c67d0e3308cb6af15ca6fb1`，`spentQuota: 0`、`spentApiRequests: 0`（浏览器路径，不耗 REST 额度）。
- 记录：`onshape_docs/verification/pending-live-verification-step-import-2026-10-03.json`
  （含三次真机尝试、`into_part_studio` 的 I4 行验证、以及**尚未**被验证的两项：
  三个选择器按记录自身口径仍未"证明必要性"；本次会话创建的页签行仍在文档里待清理）。
- 离线部分（本轮实跑）：

```
Ran 44 tests in 0.151s

OK
```

## 送达判据（用收据工具，不用 send 返回值）

出处站信均以 `mail-delivery-receipt.sh` 核查为 `found（本项目内 project_id=1）` 且收件人为**真注册身份、非影子**：
`307`（CadQ）/`310`（CadQ E6-E7）/`311`、`317`（MeshQ）/`315`、`316`（CadQ、MeshQ R14）/`318`（协调方）。
早期轮次：`264/265/266/275/276/286/287/295/296/299/300/302/303`。

## 仍在等对端（不阻塞本平面结论）

E6/E7 字段补齐、R14 一句话绑定、MeshQ 的 `label` 字段与"地址就是摘要"一句。
对应检查当前 **3/5** 与 **3/5**，**对方补上即自动变绿**。

## 本页自身可核对

```
all checks passed; stats:
```
