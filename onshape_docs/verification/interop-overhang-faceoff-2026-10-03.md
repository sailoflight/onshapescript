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
the boundary sits on: 44.9, 45.0 and 45.1 give identical results on both. I built probes that can:
a right-triangular prism with `H = W·tan(θ)` fixes one sloped face at exactly θ
(`/tmp/three-plane-drop/onshapescript-overhang-boundary/`, outside every repository, with `probe.json`
and `measured-onshapescript.json`).

| Probe | My `overhangAreaMm2` at 45.0 | Closed form | Meaning |
|---|---|---|---|
| `wedge_tilt_44.95.stl` | **965.192416792** | base 400 + slope 565.192416792 | a face at 44.95 is counted |
| `wedge_tilt_45.05.stl` | **400.000000000** | base only | a face at 45.05 is not |
| `plate_theta_45.00.stl` | **440.0** | 400 + 40 | **float noise decides at exactly 45.0** — both faces entered |
| `plate_theta_45.05.stl` | **40.0** | side face at 44.95 only | the counted set switches sides across 45 |

So the boundary is **strict `<`** on both sides, deterministically testable with 44.95/45.05, and
exactly-45.0 must never be used as a boundary test.

## Findings that only the face-off could produce

1. **`faces` is two different units.** Their `faces` counts merged planar faces, mine counts triangles:
   cube 1 vs 2, sphere 512 vs 960 (512 = 64 pole triangles + 7 rows × 64 quads; 960 = 64 + 7×64×2).
   Same area to 1e-9 and a 1.875× count difference. The field must be
   `counted_triangles` / `counted_planar_faces`, never a bare `faces`.
2. **Watertight ≠ outward-wound.** My first wedge had one inward-wound sloped face. This analyzer
   reported `watertight: true` and silently dropped that face (400.0 instead of 965.192416792).
   Three gaps in `fdm_analysis/metrics/stl_geometry.py`, found from the outside:
   - no orientation-consistency check (a consistently oriented closed mesh traverses every shared
     edge once in each direction; that test catches the inverted face exactly),
   - no `facesWithoutNormal` count (MeshQ publishes one; this analyzer's answer is "not measured",
     which is not the same as 0),
   - no counted-element count, only the summed area.
   MeshQ's rule — trust a face normal only after checking the winding — is the correct discipline and
   this analyzer does not yet meet it.
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
