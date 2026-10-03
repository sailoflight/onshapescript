# Cross-plane join of the 70-piece handoff against CadQ's manifests (2026-10-03)

**What this record settles:** whether the agreed identity/addressability rule survives contact with a real
peer artifact — `index` vs exact volume vs identity tuple vs digest — and which of two disagreeing readings
the bytes themselves support. Everything below was read from the two manifests and from the delivered STL
bytes; **no geometry kernel was re-run**, so nothing here depends on a kernel verdict.

## Artifacts joined

| Side | Artifact |
|---|---|
| CadQ (producer) | `cad_agent/output/three-plane/gf-storage-v25-U-two-legs-lin0.05-ang0.1/manifest.json` (70 solids, `cadq.step-tessellation/0.2`, `handoff_schema: onshapescript.handoff/0.4-draft`) and the `…-lin0.05-ang0.3` sibling |
| onshapescript (verification handoff) | `/tmp/three-plane-drop/onshapescript-70piece-tessellation/manifest.json` (70 pieces, produced at the **ang 0.1** tolerances CadQ declared: `used = {linear 0.05, angular 0.1}`) |

Raw outputs: `join-vs-cadq.json`, `join-bytes-verdict.json` (both in the drop directory).

## 1. Index join (positional addressing)

| Compared | vs CadQ ang0.1 | vs CadQ ang0.3 |
|---|---|---|
| STL byte identity (sha256) | **70/70** | 39/70 |
| triangle count | 70/70 | 39/70 |
| exact B-Rep volume (bit-for-bit) | **70/70** (delta `0.0` on all 70) | 70/70 |
| exact B-Rep bounds | 70/70 within 1e-5 mm (delta `0.0` on all 70; `==` on the dict is 26/70 only because of nested-field noise) | same |
| mesh-vertex bounds | 54/70 within 1e-5 mm — **16 differ, and the bytes say whose field is wrong** (below) | same |
| worst mesh-volume difference | **2.41e-6 relative** on identical bytes | 9.13e-4 |

The ang0.3 column is the expected result of a different deflection (fewer triangles, 39 pieces coinciding);
its usefulness is as a control: the *reading* comparison changes with tolerance while **the exact B-Rep
volume does not** (70/70 bit-identical in both).

## 2. Which side is wrong about the box — decided by the bytes

The two producers' STL files are byte-identical, so there is one true vertex box and both fields can be
checked against it:

| Field | Equals the artifact's own vertex box |
|---|---|
| onshapescript `parts[].bounds_mm` (`boundsAlgorithm: tessellation_vertices(artifact_bytes)`) | **70/70** |
| CadQ `solids[].tessellation.bounds_mm` | **54/70** (16 differ, max gap `1.2207e-05` mm) |

Example, piece #3:

```
bytes' own vertex max : [399.8999938964844, 379.20001220703125, 227.5]
CadQ tessellation max : [399.9, 379.2, 227.5]          <- the EXACT value, not the mesh's
CadQ brep (exact) max : [399.9, 379.2, 227.5]
onshapescript mesh max: [399.8999938964844, 379.20001220703125, 227.5]
```

So the gap is not geometry: CadQ's **mesh** bounds field carries the **exact** value on those 16 pieces.
A consumer comparing its own vertex box against the manifest would see a spurious 1.2e-05 mm discrepancy —
and would be right to refuse the field, because the bytes are identical.

The same join **clears** CadQ of the trap this repository fell into: its `brep.bounds_mm` equals this
repository's **pre-export** exact box with delta `0.0` on 70/70 pieces, so it does *not* measure after an
export that mutates the cache (this repository's own defect, `380.0000001000 → 380.0008703904`).
*(An earlier reading of mine suggested CadQ had the same trap; the 1e-5 comparison disproved it, and the
correction is recorded here rather than left in a message.)*

## 3. Identity join (the addressability question)

| Addressing | Result |
|---|---|
| by index | consistent here, but it is an ordering — a re-export can reorder, so it is a display convenience, never the identity |
| by exact volume alone | **cannot address this assembly**: 14 duplicate value groups cover **60 of 70** pieces, largest group **8** |
| by the identity tuple (`brepVolumeMm3` + mesh-family `bounds_mm`, declared quanta) | **multiset equal 70/70** in both directions, nothing left over on either side |
| by digest | transfer only, and rules first: this repository's own set signature moved `ade4c12ab2b91fc5… → 7f4271064f1107bebb3aaaf4…` with the geometry untouched (canonical form changed); MeshQ measured CadQ's signature moving between schema 0.1 and 0.2 with every STL byte unchanged. Hence `identity_rule.version` / `signature_schema` |

Measured consequence for the contract: **the digest is not the identity and the volume is not an address**;
the tuple is, and it is checkable by the consumer from the bytes it holds.

## 4. What this record does not claim

* Not a kernel-independence claim: both sides ran the same OCCT build (`cadquery+OCP 2.8.0+OCCT-7.9.3.1`),
  and both record `independent_kernel: false`. Agreement here proves **rule reproducibility**, which can
  catch implementation drift — not geometric truth.
* Not a printability claim: no slicer is installed on this host (`fdm_analysis/README.md`), and the
  print-fit split is drafted separately in `docs/roadmap/PRINT_FIT_INTERFACE_DRAFT.md`.
* The mesh-volume difference (2.41e-6 relative on identical bytes) is reported as a *measurement* difference;
  which side is closer to the truth is **not** settled here, because that needs a third reader on the same
  bytes (MeshQ already reads them, so that comparison belongs to the next round).
