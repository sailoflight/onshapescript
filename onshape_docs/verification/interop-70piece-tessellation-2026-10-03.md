# 70-piece STEP tessellation: one handoff, read independently by two implementations

**Date:** 2026-10-03. **Producer:** onshapescript (`fdm_analysis/conversion/step_tessellation.py`).
**Source:** `/home/lijq/code/CadQ/gf-storage-v25-U-two-legs.step`, 12,227,700 bytes,
sha256 `b4a5369e1d7b8b66…`. **Drop directory:** `/tmp/three-plane-drop/onshapescript-70piece-tessellation/`
(the neutral directory agreed over the mailbox, outside every plane's repository).

This record exists because two numbers had already been wrong once in this round: a face winding that
this repository reported as `watertight` while a face was inverted, and a per-piece batch (MeshQ's) in
which 45 of 70 rows described other pieces. Both were caught by an **independent** route, so every
number below names the measurement that produced it rather than the tool that was asked.

## 1. What exists now

| Artifact | Path | Fact |
|---|---|---|
| manifest (v0.4 draft shape) | `<drop>/manifest.json` | `schema: onshapescript.handoff/0.4-draft`, 70 part rows |
| per-piece STL | `<drop>/parts/part-0000.stl` … `part-0069.stl` | 30,893,280 bytes total, 70 files |
| reproducibility mirror | `<drop>/reproducibility/parts/…` | a **second** full tessellation, used only to digest-compare |
| first-pass probe | `<drop>/raw-tessellation-onshapescript.json` | the raw run before the manifest was assembled |
| cross-check | `<drop>/cross-check-vs-meshq.json` | this page's per-piece join, machine-readable |

Totals, measured by `fdm_analysis.metrics.stl_geometry` (see §3 for why that matters):

| Quantity | onshapescript | MeshQ (isolated re-run) | relative difference |
|---|---|---|---|
| pieces | 70 | 70 | — |
| triangles | **617748** | **617748** | **0 (0 mismatching pieces)** |
| overhang area, 45°, downward-face policy | **745683.937023449 mm²** | 745683.839054 mm² | 1.31e-7 |
| surface area (the denominator) | **2796354.139889901 mm²** | 2796354.068928 mm² | 2.53e-8 |
| overhang ratio | **0.266662912** | 0.266662883 | 1.06e-7 |
| bed-contact area (same policy, threshold → 0) | 523856.317578745 mm² | not reported | — |
| winding (`consistent`) | **70/70** | **70/70** | 0 disagreements |

Per-piece maximum relative difference: **3.39e-6** (surface area), **2.60e-6** (overhang area). The
aggregate differences are smaller than the per-piece maximum, which is what cancellation looks like —
a per-piece-agreeing pair of implementations does not have to agree better in the sum, and quoting only
the sum would have hidden the largest disagreement.

**CadQ's independent count is the third leg:** MeshQ read `triangle_count` = 617748 in CadQ's manifest
and used it to disprove its own polluted batch (793076 counted faces for a 617748-triangle set is
impossible for a subset). This run reproduces 617748 exactly, so the counting rule now has three
implementations on one number.

## 2. `sha256_stable: true` with evidence, and byte identity across producers

`sha256_stable` defaults to false in this repository because two real Onshape STEP exports of one
geometry differ by 34 header bytes. For the mesh handoff the same claim had to be **measured**, so the
producer tessellates every solid **twice** and records both digests per piece:

* 70/70 pieces produced **byte-identical** STL files in the two runs → `mesh.sha256_evidence` carries two
  equal digests per piece, and `reproducibility.unstablePieces` is `[]`.
* Cross-producer: this run's `part-0000.stl` is **byte-identical** to the copy MeshQ measured
  (`106a29a606a6b5cba89cb0b30ed09e9776830e2e3e952ddaf262e9c16bc541f7`, 52,284 bytes, no differing byte).
  Same kernel, same declared tolerances, same file name → same bytes, so here the digest really is a
  transfer-integrity check.
* The digest that is *not* stable-by-construction is the source STEP's (header GUID + timestamp). The
  manifest therefore sets `identity.sha256_stable = false` on the **source** and `true` on the **mesh**,
  and in both cases states which artifact it describes.

## 3. What this does and does not prove

**Independent here:** the measurement. Every mesh number above comes from
`fdm_analysis.metrics.stl_geometry` (this repository's own Python analyzer), which is a different
implementation from MeshQ's kernel — so the 1.3e-7 aggregate agreement is a real cross-implementation
check on the *policy and its arithmetic*, and the 0/70 triangle and winding disagreements are a real
agreement on the *counting and orientation rules*.

**Not independent here, and said so in the manifest:** the tessellation itself ran on CadQ's
interpreter (cadquery+OCP 2.8.0 / OCCT-7.9.3.1) because that is the only OCCT build reachable from this
machine. The manifest's `tessellation.independent_kernel` is therefore **false** with a `kernel_note`
explaining it, and the exact-volume total reproducing CadQ's `3035486.8177026636 mm³` **bit-identically**
is a rule-level reproduction, not a second kernel's verdict. CadQ made this distinction first and was
right to: the same mistake was made earlier in this session and corrected.

**Neither result is a printability verdict.** Both sides count "downward-facing area" with the
bed-contact faces included; `worst_tilt_deg`-style geometry near the threshold is decided by computed
floats, which the contract already calls a convention rather than an error (see
`interop-overhang-faceoff-2026-10-03.md`).

## 4. Reproduce

```bash
# the drop directory holds the artifacts; the producer lives in this repository
/home/lijq/code/CadQ/.venv/bin/python - <<'PY'
import sys; sys.path.insert(0, "/home/lijq/code/onshapescript")
from fdm_analysis.conversion import step_tessellation as st
m = st.tessellate_step(
    step_path="/home/lijq/code/CadQ/gf-storage-v25-U-two-legs.step",
    output_dir="/tmp/three-plane-drop/onshapescript-70piece-tessellation/parts",
    declared_by="cadq", used_by="meshq", export_id="gf-storage-v25-U-two-legs",
    linear_tolerance_mm=0.05, angular_tolerance_rad=0.1, reproducibility_check=True,
    independent_kernel=False)
st.write_handoff_manifest(m, "/tmp/three-plane-drop/onshapescript-70piece-tessellation/manifest.json")
PY
# offline contract tests (no CadQuery, no browser, no Onshape request)
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=temp/browser-common-site .venv/bin/python -m unittest \
  dev/tests/test_step_tessellation.py dev/tests/test_stl_geometry.py
```

## 5. Contract consequences this run settles

1. **Tessellation determinism is measurable, so `sha256_stable` can be `true` with a receipt** — but only
   per artifact, and only because a second run was actually made.
2. **`elements` counts need a name, not a bare `faces`** — three implementations agree on 617748 only
   because each says *what* it counts (`triangleCount` vs merged planar faces).
3. **The denominator must travel with the ratio** — `surfaceAreaMm2` is published for exactly this
   reason; "26.67 % overhang" was unreadable without it.
4. **An aggregate is not a substitute for per-piece rows.** The two agreements above are aggregate-level
   *and* per-piece; the batch that lost 45 of 70 rows was caught only because a per-piece independent
   count existed to compare against.
5. **`applicable` gates travel per piece**: a piece with an inconsistent winding gets `volume_mm3: null`
   and `applicable.volumeMm3: false` rather than a number with a caveat (contract v0.4 §2d row 16).
