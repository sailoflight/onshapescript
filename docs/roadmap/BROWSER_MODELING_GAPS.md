# Browser modeling capability gaps (roadmap)

Status: geometry, drawing, and active non-Bambu FDM gaps resolved 2026-08-26; Windows Bambu deferred

This roadmap records the concrete tool capabilities exposed by a real modeling
round (100mm PU duct -> 12025 fan exhaust adapter, 2026-08-24) and their
subsequent resolution. Current behavior keeps a complete registry and exposes a
semantic default view as described by `../architecture/OVERVIEW.md`. Follow the
optional six-level semantics defined in `DYNAMIC_TOOL_DISCOVERY.md`: L1/L2 are
generic browser primitives/transactions, L3 is an Onshape interaction, L4 is one
verified Onshape transaction or observation, L5 is a multi-transaction workflow,
and L6 is an independently consumable deliverable. Project control is outside
L1-L6.

Ownership stays with the `browser` module (`onshape_browser_mode` +
`mcp_main/win/mcp/browser_tools.py`); the items below are implemented and retain
their original gap narrative for provenance.

> The complete six-level FS-mode semantic tool surface — focused on the
> **FS script mode** (deploy/compile-status/symbols/parameter-edit) plus its
> Part-Studio coupling points (part context-menu drawing auto-views), with
> improvement suggestions for existing tools — is planned in
> `BROWSER_FS_SEMANTIC_TOOLS.md`. This page stays focused on the concrete gaps a
> single real modeling round exposed. Note that `BROWSER_FS_SEMANTIC_TOOLS.md`
> currently treats **native feature-mode** transactions (sketch/extrude/
> fillet via the Part Studio toolbar) as out of scope; the spiral/screw-on
> ridge item below is therefore deferred from the FS-mode plan unless a native
> transaction is separately re-approved.

## 1. Thread / screw-on spiral generation (L5)

A screw-on connection for a spiral-reinforced PU duct was a design goal.
`externalThread` only handles standard ANSI/ISO sizes and cosmetic attributes,
not a custom coarse pitch such as the ~12.7 mm PU-duct wire pitch.

Resolution: `browser_spiral_ridge` accepts bounded numeric radius/pitch/profile/
length parameters, rejects more than 10000 revolutions, generates a fixed
`opHelix` + rectangular-profile `opSweep` FeatureScript, then reuses the
compiler-gated browser deploy/apply workflow. It exposes no raw script or CSS
input, supports dry-run/confirmation, and requires deployed+built acceptance.
The generated script passes the local FeatureScript static checker. This is a
FeatureScript-backed workflow, not an unsupported native-toolbar helix guess.

## 2. FDM print analysis and delivery (L4 -> L6)

Correction:

- `browser_print_orientation_check` opened Onshape draft analysis. That surface
  cannot establish FDM bed contact, support demand, bridge behavior,
  center-of-mass stability, print height, layer strength, build volume, or
  profile-specific slice results. It was cataloged `semantically_invalid` and
  default-hidden, and on 2026-09-19 it was archived rather than kept as
  compatibility code; the gap it names is still open
  (`../history/legacy/ARCHIVED_BROWSER_PRINT_TOOLS.md`).
- `browser_wall_thickness_report` is only an L4 sampled UI observation; it is not
  a global mesh wall-thickness result.
- `browser_apply_blend` remains one L4 Onshape transaction.
- `browser_print_optimize_part` was structurally L5, but its invalid orientation
  dependency and apply-before-assessment ordering meant it could not be treated
  as a valid FDM workflow; it was archived in the same pass.

The replacement uses canonical STEP from browser or REST source adapters,
explicit STEP tessellation, and the shared root-level `fdm_analysis` library.
Browser owning tools now provide L4 STEP acquisition/readiness plus an L6
STEP/STL/report/manifest package; REST has the equivalent mock/replay-verified
transport and offline package wrapper. The adjacent CadQuery 2.8.0 / OCP 7.9.3.1
backend was field-validated on a real browser export. Windows Bambu slicing stays
explicitly deferred and is not part of the accepted non-slicer package. The
detailed staged record is `BROWSER_SIX_LEVEL_SEMANTICS_AND_FDM_PLAN.md`.

## 3. Drawing auto-view insertion from a part (L5)

The drawing tab was created but stayed an empty sheet: `browser_create_drawing`
and `browser_draw_part` complete the source/template dialog but do **not** pick
the view-mode option ("四个视图"/"没有视图") and do **not** insert automatic
views. Verified user knowledge: an auto-view drawing is created **from a
specific part's context menu ("创建工程图")**, not from the generic drawing
creation dialog. The current `create_drawing` semantic
(`onshape_browser_mode/semantic.py`) never selects the view layout, so the
result is a blank sheet with no views.

Resolution: `browser_drawing_insert_views` targets an exact Part Studio part row
and exact `创建 <name> 的工程图…` command, selects a semantic view layout, requires
exactly one new drawing tab, and verifies view content through a Drawing DOM
node or decoded main-canvas ink distribution. `browser_draw_part_with_views`
composes this with dimensions. The legacy `browser_draw_part` now rejects an
empty dimension list, removing the `all([])` blank-sheet false positive.

The live four-view canvas fixture, pixel metrics, and selector limitations are
stored under `dev/button-map/scan-app-shell.json` and
`scan-drawing-four-views.png`.

## 4. Native-toolbar modeling (re-tested and rejected) vs thin-feature tree (adopted)

D5 (`FS_FIRST_CONTROLLING_ROUTE.md`) says the browser leg must not model geometry by
driving Part Studio toolbars, dialogs, and context menus. A "build it as a feature
tree" request is the one requirement that looks like it needs that route, so D5 was
re-tested end to end on 2026-09-20 with a full native spike: two staged, resumable
project fixtures (`native-plate-sketch`, `native-plate-extrude`), a
`modeling_transactions` module driving 草图 → plane row → rectangle → typed
dimensions → 拉伸 depth, per-stage screenshots for cross-host review, and its own
test module — roughly 700 lines of tests that kept every viewport click inside the
graphics box. The spike was **rejected and reverted**; the patch is kept as
`temp/native-spike-rejected.patch` (local-only, `temp/` is gitignored, so the
decision record here is the durable part, not the file).

The requirement it was meant to satisfy is satisfied a different way, and this is
the part worth keeping: **a native modeling step and a thin custom feature call the
SAME standard-library routine.** `extrude(context, id, definition)` is what
Onshape's own 拉伸 dialog runs, so a thin `Thin Extrude` row is not an imitation of
a modeling step — it is that step, with its numbers exposed as dialog parameters a
human edits in the Feature List. D5 therefore stands unamended in what it forbids
(GUI button-driving), and the feature-tree requirement is met inside FeatureScript.

Measured outcome (2026-09-21): a 14-row chain of `Thin Sketch Rectangle` /
`Thin Sketch Circle` / `Thin Extrude` reproduced the three-row domain baseline's
solid exactly — volume `39547.5903 mm³`, surface area `20002.2154 mm²`, 194 faces,
zero delta in each, same nine face families including 4 x R4 outer corners and 16
cones at exactly 45.0 deg per band. Evidence:
`onshape_docs/verification/thin-feature-rebuild-brep-2026-09-21.md`; the two dialog
traps that had to be solved first (`change`-event commit, non-clickable styled
checkbox) are recorded in `onshape_docs/experience/featurescript.md`.

Consequences for the registry:

- `browser_insert_custom_feature` accepts explicit `parameters`, so one transaction
  creates a thin row *with its numbers* instead of insert-then-edit, and it refuses
  the insert when a filled field did not commit (a refusal leaves a real
  default-valued row that must be deleted before retrying).
- A project may express a whole part as an ordered list of thin rows; the fixture
  `dev/fixtures-capture/gridfinity-thin-plate.json` is the reference example.
- No new native-transaction tool is added, and `BROWSER_FS_SEMANTIC_TOOLS.md`'s
  "native feature-mode out of scope" boundary is unchanged.

## Summary table

| # | Resolved capability | Level | Module / capability family | Implemented acceptance |
|---|---|---|---|---|
| 1 | Spiral / screw-on ridge generation | L5 | browser.partstudio / FeatureScript workflow | bounded helix+sweep script + compile/deploy/apply verification |
| 2 | FDM analysis and delivery | L4 -> L6 | shared `fdm_analysis` + browser/REST source adapters | draft proxy invalid; real browser AP242 STEP + CadQuery/OCP STL + verified non-slicer L6 package; Bambu deferred |
| 3 | Drawing auto-view insertion from a part | L5 | browser.drawing | exact new tab + DOM or decoded canvas view evidence |
| 4 | Modeling a part as a feature tree | L5 | browser.partstudio / thin FeatureScript rows | 14 thin rows reproduce the domain baseline's solid with a zero-delta B-rep fingerprint (volume, surface area, 194 faces, all nine face families) |

## Provenance

Identified during the 2026-08-24 modeling round: new document
`100mm PU duct to 12025 fan adapter` (Part Studio 1, one verified part
`100mm duct fan adapter`); Drawing 1 was created blank and spiral/print
transactions were absent. The 2026-08-25 implementation resolves the geometry
and Drawing tool surface while preserving the conservative unknown/sample print
results. The later six-level review identifies the draft-analysis FDM dependency
as semantically invalid; the 2026-08-26 browser STEP/CadQuery field run closes the
active non-Bambu deliverable gap. The original part model and FeatureScript live under `../../examples/duct-fan-adapter/`.
