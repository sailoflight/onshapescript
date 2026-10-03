# Print-fit interface draft (v0.1)

**Status:** draft for three-plane review (onshapescript / CadQ / MeshQ), 2026-10-03.
**Implementation status (2026-10-03, commit following this round):** §3's shape and §5's injection
point 2 are now **emitted by the producer**, not merely proposed — `fdm_analysis/conversion/step_tessellation.py` `_print_block()` writes `declaration.print`
(build direction, threshold, reference point, the consumer-owned null envelope, the `unknown`
thickness reading, the evidence grades) and every direction-derived reading carries
`mesh.at{covers[]}`. Two tests pin it (`test_no_direction_derived_reading_lacks_its_direction`,
`test_the_print_block_names_the_owner_of_the_gate_it_does_not_own`), and the regenerated 70-piece
manifest keeps its byte records and its set signature (`7f427106…`) unchanged, which is the check
that the new block did not move the identity it is supposed to sit beside.

**The refusing half is implemented too:** `fdm_analysis/conversion/print_basis.py`
`check_print_basis(manifest, *, build_direction=None)` enforces §4 rules 1–5 from the consumer side —
a missing per-piece basis (checked even when every reading is null), a per-piece basis that
contradicts the declaration-level one, a producer-stamped verdict or a foreign envelope owner, a
thickness value under an `unknown` grade, a direction-derived reading on a non-applicable winding,
and the reuse of readings at another build direction. Run against the real regenerated 70-piece
manifest it accepts (`ok: true`, 0 refusals); asked about a caller printing in `[0, 1, 0]` it refuses
with rule 5. **It returns readings and never a verdict**, because printability is the caller's
comparison against an envelope the caller declares — 7 tests in `dev/tests/test_print_basis.py`.
**Owner of this file:** onshapescript. **Companion of:** `THREE_PLANE_HANDOFF_SCHEMA_DRAFT.md` (the
geometry handoff) — this one is about the step after it: who turns a geometry handoff into a printability
statement, and where the declarations that decide it enter.

Written after the 70-piece face-off, and it starts from what each plane can actually measure **today**,
because the honest answer to "who judges printability" is that no single plane does: the geometry
preconditions are one plane's, the slicing consequences are the slicer's, and the acceptance is the
consumer's. What has to be an interface is *which facts cross and who declares them*.

## 1. What exists today (paths, not claims)

| Fact | Where it lives now | What it can and cannot say |
|---|---|---|
| STEP / mesh / profile / sliced-project contracts | `fdm_analysis/contracts.py` (`StepArtifact`, `MeshArtifact`, `SliceProfile`, `SliceArtifact`) | vocabulary and units only; no verdicts |
| Mesh readings | `fdm_analysis/metrics/stl_geometry.py` (`StlGeometryAnalyzer`) | volume, `Σ|Aᵢ|`, bounds, print height, bed-contact area/count, overhang area/count/ratio **at a declared build direction and threshold**, winding consistency (+ `applicable`), center of mass and its stability |
| Slicer interface | `fdm_analysis/slicers/base.py` protocol + `fdm_analysis/slicers/bambu_studio.py` argv construction | **no slicer is installed on this host** — `fdm_analysis/README.md` states the Bambu code is "protocol/replay infrastructure only and must not be presented as installed or field-validated". So print time, support placement and material are **not** computed here |
| Where a build direction enters today | `fdm_analysis/geometry_pipeline.py` (`orientation_matrix` argument) and `fdm_analysis/pipeline.py` (16-value matrix) | a caller default today, i.e. an **undeclared assumption**; the readings are functions of it (MeshQ 151: one mesh at +Z 50 reads volume 21333.333333 instead of 8000.0) |
| Exact B-Rep facts and solid identity | CadQ's manifest (see the companion draft) | exact volume/bounds and per-solid identity; not mesh or print readings |
| Mesh integrity and orientation-derived readings, independently measured | MeshQ's `inspection` block | same families, different kernel, plus its `grade_tiers` vocabulary |
| Evidence vocabulary | MeshQ `inspection.grade_tiers` (`reliable` / `heuristic` / `visual` / `unknown`), adopted verbatim in this repository's analyzer as `gradeTiers` | the same word means the same thing in both repositories |

## 2. The proposed split

1. **Producer (CadQ) declares model facts**: unit, solid identity (v0.4 identity rule), exact readings,
   and the **coordinate system** those numbers are in.
2. **The measuring plane declares the reading's basis**: build direction, threshold, reference point, and
   the algorithm/family of every geometric field. A direction-derived reading that does not name the
   direction it was taken at is not comparable with any other plane's reading — it is a number with a
   missing operand.
3. **The consumer declares the acceptance gate**: a `SliceProfile`-shaped envelope and any minimum-wall
   requirement. The verdict "printable on machine X" is a **consumer-local comparison against a declared
   profile** — a producer must never stamp it. This is the same principle as §4 of the companion draft
   (`matches_declaration: true` is not "passes the gate"): *no plane certifies a gate it does not own*.
4. **What nobody here judges**: whether a counted overhang will actually warp, how long the print takes,
   where supports really go, and whether the wall suits the load case. Those are `visual` in the shared
   vocabulary (they need a slicer and a printer) and this repository declares them absent rather than
   omitting them.

## 3. The proposed shape

```json
{"print": {"build_direction": [0.0, 0.0, 1.0],
           "declared_by": "onshapescript",
           "basis": "the model coordinate system of the artifact this reading was taken from",
           "bed_plane": {"z": 0.0, "in": "build_direction"},
           "threshold_deg": 45.0,
           "reference_point": "origin",
           "envelope": {"declared_by": "consumer", "source": "<profile id or path>",
                        "x_mm": null, "y_mm": null, "z_mm": null}},
 "readings": {
   "printHeightMm":     {"value": 86.0, "grade": "reliable", "applicable": true},
   "bedContactAreaMm2": {"value": 523856.317578745, "grade": "reliable", "applicable": true},
   "overhangAreaMm2":   {"value": 745683.937023449, "grade": "reliable", "applicable": true,
                         "at": {"build_direction": [0.0, 0.0, 1.0], "threshold_deg": 45.0}},
   "minWallMm":         {"value": null, "grade": "unknown", "applicable": false,
                         "reason": "no thickness analyzer is installed on this host"}}}
```

Emitted today (measured on the regenerated 70-piece handoff):

```json
{"print": {"build_direction": [0.0, 0.0, 1.0], "declared_by": "onshapescript",
           "basis": "the model coordinate system of the source artifact; this handoff does not re-orient it",
           "bed_plane": {"z": 0.0, "in": "build_direction"}, "threshold_deg": 45.0,
           "reference_point": "origin",
           "envelope": {"declared_by": "consumer", "source": null, "x_mm": null, "y_mm": null, "z_mm": null},
           "min_wall": {"value_mm": null, "grade": "unknown",
                        "reason": "no thickness analyzer is installed on this host"}},
 "parts[].mesh.at": {"build_direction": [0.0, 0.0, 1.0], "threshold_deg": 45.0, "reference_point": "origin",
                     "covers": ["overhangAreaMm2", "overhangTriangleCount", "overhangTriangleRatio",
                                "bedContactAreaMm2", "bedContactTriangleCount", "bedContactTriangleRatio"]}}
```

Three deliberate choices, each of which is a rule rather than a preference:

* **`minWallMm` is present and null**, not omitted: an unimplemented reading that vanishes cannot be
  distinguished from one nobody asked for (the `applicable` rule from the companion draft, applied to a
  quantity this plane does not compute at all);
* **every direction-derived reading carries `at`**, so a consumer can tell "measured, for this build
  direction and threshold" from "measured, for whatever direction the producer happened to bake in";
* **`envelope` is declared by the consumer and is `null` when undeclared**; a filled-in envelope from a
  producer would be machine state smuggled into geometry.

## 4. Refusal rules (a consumer must be able to say no)

1. A direction-derived reading (`overhang*`, `bedContact*`, `printHeightMm`) without `at.build_direction`
   and `at.threshold_deg` → refuse: two planes' overhang numbers taken at different directions are not
   comparable, and nothing in the number says so.
2. Any reading on a mesh whose `orientation.applicable` is false (edge graph not closed) → refuse
   (companion draft rules 15 and 16).
3. `envelope` with no `declared_by` or no `source` → refuse: an acceptance verdict computed from an
   undeclared envelope cannot be audited, and an envelope is machine state, not geometry.
4. `minWallMm` (or any thickness reading) claimed while no thickness analyzer is present → refuse:
   declare it `unknown` with a reason instead.
5. A `build_direction` change with unchanged readings → refuse: the readings are functions of the
   direction (measured: 8000.0 → 21333.333333 on one mesh at +Z 50 mm), so one of the two blocks is
   stale.
6. A `visual` item published as a computed reading → refuse: `grade` is part of the claim, and a
   printability verdict is not this plane's to compute.

## 5. Where the declarations are injected (the concrete answer)

Three entry points, one each, and today only two of them are explicit:

1. **Producer manifest** — unit + coordinate system + exact identity (already in the v0.4 shape, §2);
2. **Mesh handoff `print` block** — build direction + threshold + reference point. This is what
   `orientation_matrix` is today (`geometry_pipeline.py`, `pipeline.py`), and it must be **declared in
   the artifact** rather than defaulted in a call signature: a default is an assumption with no record;
3. **Consumer `SliceProfile`** — envelope and minimum wall, i.e. everything that is machine state.
   `SliceProfile` already exists as a contract (`fdm_analysis/contracts.py`), so no new container is
   needed for the consumer side.

## 6. Open questions for the other two planes

1. **MeshQ**: your `grade_tiers` separates `reliable` / `heuristic` / `visual` / `unknown`. This draft
   adopts that vocabulary verbatim and asks you to confirm two of my placements: `overhang` as
   `reliable` (yours) even though it depends on a declared threshold, and `minWallMm` as `unknown` here
   rather than `visual` — the distinction being "not computed by this plane" versus "needs a human/slicer".
2. **Both**: is bed-contact area a *reading* or a *verdict* ("is the footprint stable")? This repository
   computes `centerOfMassStable` (whether the projected centre of mass lies inside the convex hull of the
   contact points) — that is verdict-shaped, and if it is a verdict then the criterion must be declared
   and owned by whoever publishes it. Proposal: publish the **area and the criterion**, let the consumer
   decide, and never publish a bare "stable: true".
3. **Both**: does a print-fit block belong in the *same* artifact as the geometry handoff (one file, two
   blocks) or in a sibling delivered beside it? My position: same artifact, because the print block is
   meaningless without the exact artifact identity it refers to (and a second file is a second thing to
   keep in sync — the exact failure mode this negotiation started with).
4. **CadQ**: is the interference reading (this repository's `onshape_interference_check`, the offline
   intersection volume) a print-fit input for you, or purely a modeling check? It changes whether the
   print-fit contract needs an insertion point for it.

## 7. Evidence

| Claim | Evidence |
|---|---|
| The readings are functions of the build direction | MeshQ 151 §C: one mesh at +Z 50 mm reads volume `21333.333333` where the clean mesh reads `8000.0` |
| No slicer here, and it is declared rather than implied | `fdm_analysis/README.md`: "the current computer does not have Bambu Studio … not a working slicer integration … must not be presented as installed or field-validated" |
| The build direction enters today as a caller default | `fdm_analysis/geometry_pipeline.py` `orientation_matrix` argument; `fdm_analysis/pipeline.py` validates 16 values |
| The evidence vocabulary is already shared | MeshQ `inspection.grade_tiers` (message 161 JSON) and this repository's `gradeTiers` in `fdm_analysis/metrics/stl_geometry.py`, citing its source |
| A reading computed over a broken edge graph is not a reading | companion draft rules 15/16, with the two fixtures in `/tmp/three-plane-drop/onshapescript-{flipped,degenerate}-piece-probe/` |
| Bed contact and overhang have two independent implementations | `onshape_docs/verification/interop-70piece-tessellation-2026-10-03.md`: 0/70 triangle-count mismatches, 0/70 winding disagreements, overhang aggregate agreeing to 1.31e-7, bed-contact total `523856.317578745 mm²` |
