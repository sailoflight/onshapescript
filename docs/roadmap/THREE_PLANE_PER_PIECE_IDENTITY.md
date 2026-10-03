# 逐件身份与寻址：三家**实测**的三种模型（2026-10-04）

**这一页回答目标①里的"逐件身份 / 按路径还是 sha256 寻址"**。结论：三家都给对了**摘要**，
但**"谁是地址"这件事只有两家写下来**；另外"人工可读的名字"在两家是**要推断的**，不是声明的。

工具：`dev/tools/per_piece_identity_cross_read.py`（只读离线；`--facts/--check/--json`）。

## 1. 实测：三家的逐件寻址模型（各不相同，但可对齐）

| 平面 | 一件的地址 | 稳定性声明 | 路径 | 名字 | 寻址口径写在记录里吗 |
|---|---|---|---|---|---|
| **onshapescript（本平面）** | 每件一个 `mesh.sha256`（`sha256_stable` + **`sha256_evidence`：摘要算两遍**） | ✅ `sha256_stable` + 依据 | 只留**文件名**（`mesh.path`），**不是地址** | `label: null`（**显式缺席**）+ `name`（文件名词干） | ✅ `sha256Note`（STEP 头带 GUID/时间戳 ⇒ 摘要不是下载态的不变量） |
| **CadQ** | 每个 solid 一个 `sha256`（70/70） | ✅ `sha256_stable: true` + `sha256_stable_basis: "measured"` | `solids[].path` 在摘要旁边 | `label` 字段**在**，但 **70/70 全 null** | ✅ `signature_note: 「候选过滤器不是身份：不同不构成『几何不同』，相同也不构成『几何相同』；判决在声明的等价容差下做。」` |
| **MeshQ** | **一个导出物一个摘要**（`outputs[].sha256`），并用 `objects: ["block"]` **声明它覆盖哪些件** | ✅ `sha256_stable: true` | ⚠️ **主机绝对路径** `/home/lijq/code/MeshQ/artifacts/.../block_hole.stl` | ⚠️ **没有 `label`/`name` 字段**——名字就是 `inspection.objects` 的**字典键** `"block"` | ❌ **没有**任何寻址口径声明 |

## 2. 五条规则，当前 3/5（两条 FAIL 是真缺口）

| 规则 | 结果 |
|---|---|
| `every-piece-is-reachable-from-a-content-digest` | ✅ 本平面逐件；CadQ 70/70；MeshQ 1 个摘要覆盖 1 件 |
| `the-digest-declares-whether-it-is-stable` | ✅ 三家都声明了（且都能说出依据） |
| `a-piece-names-its-label-or-says-null-explicitly` | ❌ **MeshQ 没有 `label`/`name` 字段**——名字只能从字典键**推断**（"缺席必须显式"这条在这里被绕过） |
| `no-piece-is-addressed-by-a-path-alone` | ✅ 但 **MeshQ 发的是主机绝对路径**（换台机器就不是地址；幸好摘要同时存在） |
| `the-record-states-which-address-is-authoritative` | ❌ **MeshQ 没写**；CadQ 写了（`signature_note`）；本平面写了（`sha256Note`） |

## 3. 因此①在这条上的接口结论（三条）

1. **地址 = 内容摘要，路径最多是提示**：三家的路径都**不构成**身份（本平面已把路径降成文件名，
   CadQ 把 `path` 放在 `sha256` 旁边，MeshQ 的绝对路径**不可移植**）。消费者**必须**用摘要寻址。
2. **摘要必须带"它是哪种摘要"**：`sha256_stable` + 依据（本平面把摘要算两遍当证据；CadQ 写 `measured`；
   MeshQ 写 `true`）。**这不是"身份"，是"过滤器"**——CadQ 的 `signature_note` 说得很准，本平面照抄这条口径。
3. **逐件名字要显式**：`label: null`（本平面）与 `label` 字段在、值为 null（CadQ）都是**显式缺席**，
   消费者能区分"这件没名字"与"这个记录没这个名字字段"；MeshQ 目前**只能推断**——请补 `label`（哪怕是 null）。

## 4. 附：一家给逐件摘要、一家给导出物摘要——谁对？

**都对，但必须说清覆盖面**：MeshQ 的摘要是**一个导出物**的，它用 `objects: [...]` 声明这个摘要**覆盖哪些件**，
于是消费者仍能唯一定位（导出物摘要 + 件名）。这比"假装逐件"更诚实；缺的只是那个声明本身要给一个**稳定地址语义**
（`sha256_stable` 已有，`objects` 覆盖面也已有——**只差一句"地址就是这个摘要"**）。

## 5. 重现命令（本页每个数字都出自这里）

```console
$ python dev/tools/per_piece_identity_cross_read.py --check
PASS every-piece-is-reachable-from-a-content-digest: this plane: per-part digest; CadQ: 70/70 solids carry one; MeshQ: 1 digest(s) in `outputs[]` covering [['block']]
PASS the-digest-declares-whether-it-is-stable: this plane: `sha256_stable` + the digest recorded twice as evidence; CadQ: ['True'] (basis ['measured']); MeshQ: [True]
FAIL a-piece-names-its-label-or-says-null-explicitly: ... MeshQ: no `label`/`name` field at all -- a piece's only human-facing name is its object key ['block'], so it has to be inferred from a dict key
PASS no-piece-is-addressed-by-a-path-alone: this plane reduces the path to a file name; MeshQ publishes an ABSOLUTE path (['/home/lijq/code/MeshQ/artifacts/contract-slice/work_slice_clean/block_hole.stl']) beside its digest
FAIL the-record-states-which-address-is-authoritative: CadQ: ['signature_note: 候选过滤器不是身份...']; MeshQ: none
3/5 rules passed      (exit 1)
```

**exit 1 是刻意的**：两条 FAIL 就是上面那两条缺口；对端补上后同一条命令会变成 5/5。
测试 `dev/tests/test_per_piece_identity.py`（6 条）把两侧都钉住：既断言缺口存在，也断言**本平面自己的记录五问全答得上**。
