# Browser modeling capability gaps (roadmap)

Status: proposed, not implemented

This roadmap records the concrete tool capabilities missing from the current
browser surface that a real modeling round (100mm PU duct -> 12025 fan exhaust
adapter, 2026-08-24) exposed. It is a plan, not current behavior: current
behavior is the static registry described by `../architecture/OVERVIEW.md` and
generated from `mcp_main`. Follow the four-level semantics defined in
`DYNAMIC_TOOL_DISCOVERY.md`:

- L1: generic observation/input/wait primitives.
- L2: one verified user-intent transaction with its own acceptance evidence.
- L3: a workflow composed from L2 transactions.
- L4: fixture-driven projects with assertions, checkpoints, and resume.

Ownership stays with the `browser` module (`onshape_browser_mode` +
`mcp_main/browser_tools.py`); none of these items are implemented yet.

## 1. Thread / screw-on spiral generation (L2 -> L3)

A screw-on connection for a spiral-reinforced PU duct was a design goal. The
current surface has **no atomic transaction that generates a real spiral /
helical ridge on a cylinder**. `externalThread` only handles standard
ANSI/ISO sizes and cosmetic attributes, not a custom coarse pitch such as the
~12.7 mm PU-duct wire pitch. The workaround (hand-written `opHelix` +
`opSweep` in a custom FeatureScript) is fragile and was not completed this
round.

Missing L2 tool: `browser_spiral_ridge` (or a `partstudio`-level
"add custom spiral" transaction) that, given a cylinder face, a pitch, a ridge
width/height, and a length, adds a verified helical ridge body (opHelix path +
opSweep profile, dry-run + confirmation + part-count/feature-history readback).

Follow-up L3: a "screw-on duct coupling" workflow composing flange + spigot +
spiral, with the spiral as a toggleable step so a plain spigot (hose clamp /
tape) remains the fallback.

Placement: `browser.native_modeling` / `browser.partstudio` Phase D in
`DYNAMIC_TOOL_DISCOVERY.md`.

## 2. 3D-print optimization transactions (L2)

The adapter should be print-friendly (wall thickness, fillets, draft, support
minimization, print-orientation check). Current browser surface has no
printability verification: no atomic transaction to inspect wall thickness,
overhang, or print orientation, and no transaction that auto-applies fillets /
chamfers / draft to a body.

Missing L2 tools:
- `browser_print_orientation_check` — read the current view/orientation and
  report overhang/wall-thickness risk against configured thresholds.
- `browser_apply_blend` (fillet/chamfer/draft on selected edges/faces with
  dry-run + history readback), composing the existing L1 primitives into a
  verified transaction.

Placement: `browser.native_modeling` Phase D in
`DYNAMIC_TOOL_DISCOVERY.md`.

## 3. Drawing auto-view insertion from a part (L2)

The drawing tab was created but stayed an empty sheet: `browser_create_drawing`
and `browser_draw_part` complete the source/template dialog but do **not** pick
the view-mode option ("四个视图"/"没有视图") and do **not** insert automatic
views. Verified user knowledge: an auto-view drawing is created **from a
specific part's context menu ("创建工程图")**, not from the generic drawing
creation dialog. The current `create_drawing` semantic
(`onshape_browser_mode/semantic.py`) never selects the view layout, so the
result is a blank sheet with no views.

Missing L2 tool: `browser_drawing_insert_views` — select the sheet, choose a
view layout (four views / single / iso), place the views on the sheet, and
verify the drawing frame gained geometry (canvas-image or DOM change), matching
the `browser_draw_part` frame-verification contract.

Follow-up L3: a `browser_draw_part_with_views` workflow that creates the
drawing, inserts auto-views, adds dimensions, and returns frame/view state.

Also record the operational lesson in
`../../onshape_docs/experience/browser-modeling.md` (drawing auto-views come
from the part context menu "创建工程图", not the generic dialog).

Placement: `browser.drawing` Phase D in `DYNAMIC_TOOL_DISCOVERY.md`.

## Summary table

| # | Missing capability | Level | Module / capability family | Key gap |
|---|---|---|---|---|
| 1 | Spiral / screw-on ridge generation | L2 -> L3 | browser.partstudio / native_modeling | No atomic helix+sweep transaction; externalThread is standard-size only |
| 2 | 3D-print optimization (fillet/chamfer/draft, orientation/wall check) | L2 | browser.native_modeling | No printability or blend transactions |
| 3 | Drawing auto-view insertion from a part | L2 -> L3 | browser.drawing | create_drawing never selects view layout; auto-views require part context-menu "创建工程图" |

## Provenance

Identified during the 2026-08-24 modeling round: new document
`100mm PU duct to 12025 fan adapter` (Part Studio 1, one verified part
`100mm duct fan adapter`); Drawing 1 created but blank; spiral and print
optimization not implemented. This document records only the missing tool
surface; the completed part model and FeatureScript live under
`../../examples/duct-fan-adapter/`.
