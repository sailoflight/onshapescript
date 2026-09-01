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

- `browser_print_orientation_check` currently opens Onshape draft analysis. That
  surface cannot establish FDM bed contact, support demand, bridge behavior,
  center-of-mass stability, print height, layer strength, build volume, or
  profile-specific slice results. The tool remains compatibility code but is
  marked `semantically_invalid` and default-hidden in the optional catalog.
- `browser_wall_thickness_report` is only an L4 sampled UI observation; it is not
  a global mesh wall-thickness result.
- `browser_apply_blend` remains one L4 Onshape transaction.
- `browser_print_optimize_part` is structurally L5, but its invalid orientation
  dependency and apply-before-assessment ordering mean it cannot be treated as a
  valid FDM workflow.

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

## Summary table

| # | Resolved capability | Level | Module / capability family | Implemented acceptance |
|---|---|---|---|---|
| 1 | Spiral / screw-on ridge generation | L5 | browser.partstudio / FeatureScript workflow | bounded helix+sweep script + compile/deploy/apply verification |
| 2 | FDM analysis and delivery | L4 -> L6 | shared `fdm_analysis` + browser/REST source adapters | draft proxy invalid; real browser AP242 STEP + CadQuery/OCP STL + verified non-slicer L6 package; Bambu deferred |
| 3 | Drawing auto-view insertion from a part | L5 | browser.drawing | exact new tab + DOM or decoded canvas view evidence |

## Provenance

Identified during the 2026-08-24 modeling round: new document
`100mm PU duct to 12025 fan adapter` (Part Studio 1, one verified part
`100mm duct fan adapter`); Drawing 1 was created blank and spiral/print
transactions were absent. The 2026-08-25 implementation resolves the geometry
and Drawing tool surface while preserving the conservative unknown/sample print
results. The later six-level review identifies the draft-analysis FDM dependency
as semantically invalid; the 2026-08-26 browser STEP/CadQuery field run closes the
active non-Bambu deliverable gap. The original part model and FeatureScript live under `../../examples/duct-fan-adapter/`.
