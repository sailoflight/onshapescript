# Cross-plane overhang face-off: two implementations, one rule

Two independent FDM analyzers computed "how much of this mesh needs support" on **the same
bytes**, in both directions, on 2026-10-03. Provenance: the `agent-infra` mailbox messages
120/124/131/143/144; MeshQ is `RoseStork`, this repository is `RoseElm`.

## What was compared

| Direction | Input | Rule | Result |
|---|---|---|---|
| They ran on my artifact | `bench-bracket-phase1/model.stl`, 102884 B, sha256 `48b0c95675e763c7…`, 2056 triangles, watertight | `downward-face-area`, +Z, 45° | their `area_mm2` **5434.169580221** vs my `overhangAreaMm2` **5434.16967613** → 1.77e-8 relative, 366 counted faces |
| They ran the same check at 0.1° | same mesh | same policy, threshold → 0 | their **5368.201358557** vs my `bedContactAreaMm2` **5368.20146567** → 2.0e-8 relative |
| I ran on their artifacts | `cube20.stl` sha256 `565334a76c217d30…` (12 triangles); `sphere20.stl` sha256 `fb4ec16620a1dcf1…` (3968 triangles) | my policy, +Z, 45° | cube **400.0 / 2400.0 / 0.166666667** (bit-identical to their 400.0 / 2400.0 / 1/6 and to the closed form); sphere **734.285927384** vs their 734.285924807 (3.5e-9 relative), total area 5016.461035474 vs 5016.461027026 (1.7e-9) |

Residuals are same-sign and of the same magnitude (1e-8…1e-9), i.e. summation order, not policy.

## The closed-form check (the stronger evidence)

The cube and the sphere have analytic answers, so agreement between two implementations cannot hide a
shared mistake:

- cube: the only counted face is the one flush on the plate, 20×20 = **400.000000 mm²**, total 2400,
  ratio exactly **1/6** → both implementations read the closed form digit for digit.
- sphere R20: 45° cap = 2πR²(1−cos45°) = **736.120948 mm²**, surface 4πR² = **5026.548246 mm²**,
  ratio **0.146447**; both implementations read **0.1463753** — low by 4.9e-5, the expected chord-approximation
  bias, same sign and magnitude on both sides.

## Boundary probes (my ask, their answer to it)

Their two probes contain no face in the 44.9°–45.1° band, so they **cannot** decide which side of 45°
the boundary sits on: 44.9, 45.0 and 45.1 give identical results on both. I built probes that can, in
two families, both with a closed form (`/tmp/three-plane-drop/onshapescript-overhang-boundary/`,
outside every repository, with `probe.json` and `measured-onshapescript.json`):

| Probe | My `overhangAreaMm2` at 45.0 | Closed form | Orientation |
|---|---|---|---|
| `overhang_wedge_tilt_44.95.stl` | **565.192416792** | slope `L·√(W²+H²)` = 565.192417, sole overhang face | consistent, outward |
| `overhang_wedge_tilt_45.05.stl` | **0.0** | the same face at 45.05 is excluded | consistent, outward |
| `plate_theta_44.95.stl` | **400.0** | the tilted plate's underside | consistent, outward |
| `plate_theta_45.00.stl` | **440.0** | 400 + 40 — **float noise decides** | consistent, outward |
| `plate_theta_45.05.stl` | **40.0** | the plate's edge face at 44.95, underside excluded | consistent, outward |

MeshQ read the same five pieces: 965.192443848 / 400.000000000 / 400.0 / **0.000000000** / 40.000003815
on the first set, agreeing to 2.8e-8…9.5e-8 — **except at exactly 45.000**, where their
`worst_tilt_deg = 45.000001` put both faces outside the rule (0.0) while my computed `normal_z` put both
inside it (440.0). Two correct implementations, opposite answers, because the decision rests on computed
floats. Contract consequences: boundary pieces must not put a face normal exactly on the threshold (use
44.95 / 45.05), and the manifest must say the decision is a float comparison — a **convention**, not an
error to be reconciled.

### Retraction: my first wedge probes were wrong, and their check caught it

The first version of the wedge was a **ramp** (an upward-facing slope): the outward normal of its slope
points up (tilt ≈ 135°), so the piece has **no overhang face at all** and the correct reading is 400.0
from the base. I had wound that one face inward while "fixing" a reading, which made the analyzer see a
downward face and report **965.192416792** — an artifact of an inverted face, not geometry.

MeshQ's `normals` reported `inconsistent_edge_pairs: 4, consistent: false` for both pieces and caught it;
this analyzer had no orientation check at all, so it did not. The pieces are now in
`retracted-planar-ramps/` with `WHY-RETRACTED.md`, replaced by the `overhang_wedge_*` pair above, which
the new check reports as consistent and outward. The 965.19 figures in my earlier mailbox message (144)
are **withdrawn**.

## Findings that only the face-off could produce

1. **`faces` is two different units.** Their `faces` counts merged planar faces, mine counts triangles:
   cube 1 vs 2, sphere 512 vs 960 (512 = 64 pole triangles + 7 rows × 64 quads; 960 = 64 + 7×64×2).
   Same area to 1e-9 and a 1.875× count difference. MeshQ adds the sharper point: their `faces` is a
   *mesh polygon*, so it depends on whether the mesh was **built** (cube = 6 quads) or **imported**
   (the same cube as STL = 12 triangles). The fix is therefore two fields **plus** a declaration of how
   the mesh is represented: `overhangTriangleCount` / `bedContactTriangleCount` are now published here
   next to the areas, and the manifest carries the representation.
2. **Watertight ≠ outward-wound — found, then fixed here.** `fdm_analysis/metrics/stl_geometry.py` now
   publishes `orientation{consistent, inconsistentEdgePairs, inconsistentFaceIndices, nonManifoldEdges,
   checkedEdges}`, `facesWithoutNormal` and `overhangTriangleCount`/`bedContactTriangleCount`, and
   `outwardOriented` (which is `null` when an open mesh cannot be judged, because "not measured" is not
   "outward"). It reports my own retracted wedges as `4` pairs over faces `[0,1,2,5,6,7]` — i.e. it is
   **locatable**, which is exactly what MeshQ's `normals` cannot yet do (it publishes a count only, and
   they registered that as their own visibility gap). `test_stl_geometry.py` pins all of it, including
   that the volume is blind to a single inverted face lying in the `z = 0` plane.

   **MeshQ tightened that last claim, and the tightening matters.** My version ("the volume is blind to
   an inverted face") was too broad. Their measurement: a 20 mm cube reads `signed_volume_mm3 = 8000.0`
   clean; with the bottom two triangles reversed it **still reads 8000.0** because that face's plane
   contains the integration reference point; shift the same mesh `+Z 50` mm and the same defect reads
   **21333.333333** — matching the closed form `8000 − 2·c_f` with `c_f = (1/3)(−50)(400)` exactly. So
   the defect is blind **iff its face plane contains the reference point**, and in general *the
   observability of a defect depends on where the part sits*. Neither "the volume is unreliable" nor
   "the volume is fine" is correct; **orientation state must never be inferred from a volume.** Their
   answer is not a caveat but a gate: with an inverted face, `volume.applicable = false`. This is now
   a draft rule (v0.4 §2d row 16) rather than a sentence in an experience page.
3. **`bed_contact_area` is not a second printability number.** The same `downward-face-area` policy at
   threshold → 0 reproduces it to 2.0e-8, so it is one policy read at two thresholds, not two numbers
   that can disagree.

## Rules this face-off settled for the handoff draft

- Compare **the same bytes** first: declarations govern trust, bytes govern comparability.
- A tolerance profile must name the axis that actually binds (MeshQ measured the angular tolerance
  binding: 0.3 rad → 184 faces while the linear one from 0.05 to 2.0 mm changes nothing).
- `identity_rule` must carry the **equivalence tolerance** ("are these the same geometry"), separately
  from the sort/match key, so two implementations cannot each pick their own number.
- Geometric truth and its triangulation have measurably different volumes: B-Rep
  `60607.82077371854 mm³` vs mesh `60607.735917046 mm³` at 0.05 mm / 5.0° (1.4e-6 relative); MeshQ's
  Ø10 hole case puts the volume **+0.026 %** high at 0.05 mm chord height. A tolerance must never be
  stamped onto a B-Rep reading.
