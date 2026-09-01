# Browser planned-tool implementation verification (2026-08-25)

This record covers the 22 browser tools promoted from
`docs/roadmap/BROWSER_PLANNED_TOOLS.md`. The Developer, Tester, and
Field-Evaluator responsibilities are reported separately so registration is not
mistaken for live domain acceptance.

## Scope and safety

- Onshape REST requests during this work: **0**. `LIVE_API_ENABLED` remained
  unset. The account UI later reported `742 / 2500` used; the repository's
  `apiQuota.alreadyConsumed` baseline was synchronized to 742. That historical
  account usage is separate from this run's zero-call ledger.
- Browser target: `module-interface-verification` in the persistent Windows
  browser session.
- Cloud-mutating smoke: **not executed** without a separate explicit mutation
  authorization. Dry-run and confirmation gates were verified offline.
- One FS `插入代码段` evidence click changed the editor draft. It was immediately
  undone; the browser source and maintained fixture both measured 10284 bytes
  and FNV-1a `7093403a`, proving exact restoration.
- Six-level/STEP/geometry/project-v2/dynamic-view/catalog/redundancy offline regression: **299/299 tests passed**.
- Documentation verification: **17/17 checks passed**; generated tool reference
  and docs index are current.

## Implementation verification

| Surface | Evidence | Result |
|---|---|---|
| Complete MCP registry | promoted browser definitions, semantic/dynamic gateways, bounded REST/browser STEP export, browser/REST geometry wrappers, opaque-candidate configure tools, connection tool-view control, and universal catalog; total registry count 104, no duplicate names | pass |
| Safety metadata | zero REST cost; write schemas expose pure `dry_run` and `confirm_mutation`; UI/read transactions omit cloud confirmation | pass |
| FeatureScript editor | live Module outline, exact context-menu items, Ace fold commands/widgets, toolbar Length parameter | pass (read-only evidence) |
| App shell | live document/panel/notification/share/view-cube selectors; exact share dialog | pass for observed surfaces |
| Drawing views | live 1240x694 main-canvas screenshot visually contains four projected views; decoded PNG metrics exceed view thresholds | pass (read-only fixture) |
| Print reports | tests prove unknown/unassessable and sampled/global distinctions; later six-level review marks draft-based FDM orientation semantically invalid | bounded legacy behavior passes offline; not a valid FDM engine |
| Blend and parameter edit | exact history/persistence/error acceptance paths, unit/identifier validation, dry-run/confirmation | pass offline; live mutation not run |
| Spiral ridge | bounded numeric schema; generated cylinder + helix + sweep + union FeatureScript passes local structural checks | pass offline; deploy/apply not run |
| Project control | per-tool outcome keys, closed allowlist, checkpoint/resume; drawing steps require view-bearing workflow | pass offline; no longer classified as an L6 deliverable |

## Six-level and FDM follow-up

| Surface | Evidence | Result |
|---|---|---|
| Optional semantic catalog and gateway | all 66 browser tools classified; semantic default exposes 42 browser tools (80 total with non-browser/control tools), explicit L1 8, explicit L3 12; static mode exposes all 104; ordinary ranking L5→L4→L2→L6; dependency/cycle lint empty | pass offline |
| Universal tool catalog | one immutable 104-entry index after final registration; stable SHA-256 fingerprint; modules/profiles/levels/network/mutating/current-view filters; explicit confirmation modes and local/session side effects; exact/prefix/token ranking; search 8 default/12 max, summaries ≤180 chars and no schema; exact describe only | pass offline and Windows field: buildCount=1, indexed=registry=104, visible=80, fingerprint `024126fe8d4db56aa2c493c6b3321929f5328b5a5bd929b77dbe2b3c05f4b7d0`; geometry status offline/session=false; quota module=rest; deprecated name deletion hidden |
| Connection-scoped dynamic display | semantic/static/profile/dynamic modes; seven deterministic profiles; optional browser levels; response-before-list_changed ordering; no duplicate notification; reset/reconnect; independent connection state; hidden known-name call succeeds | pass offline and Windows field: semantic startup visible=80/listChanged=false; dynamic field ordering previously response→notification; geometry profile=11; conventionOnly=true, authorityChanged=false |
| FDM fail-closed correction | compatibility orientation and optimize handlers make no browser action, do not open draft analysis, and do not attempt blend mutation | pass offline |
| Project schema v2 | legacy v1 retained; single and five-deliverable DAG fixtures produce independent L6 manifests/checkpoints | pass offline |
| Shared FDM contracts | browser/REST adapters produce the same canonical STEP type; mock converter/analyzer/slicer produce report and SHA manifest | pass offline |
| REST STEP transport | AP242 millimeter POST body, bounded no-retry polling, resumable translation ID, exact single external-data download, module-owned staging, MCP dry-run and max cost | pass mock/replay; zero live requests |
| Browser STEP transport | live-observed export dialog selectors/options; explicit URL ID match; STEP/AP242/Millimeter/direct-download configuration; non-ZIP download acceptance and browser provenance manifest | pass live: 34,084-byte STEP, SHA `2bd707bcea4666d1b7775e7c40ffc9f1d97a777f828b968905900b471711ebd3` |
| Browser geometry owning wrapper | persisted browser STEP manifest/SHA rechecked; adjacent CadQuery 2.8.0/OCP 7.9.3.1 selected through fixed WSL argv; Project v2 builds accepted L6 package | pass live-local: watertight 98-triangle STL and complete geometry metrics; zero REST |
| Bambu/artifact protocol infrastructure | Windows-native and WSL interop adapters share command specification; Windows-local staging, WSL `/mnt/<drive>` mapping, UNC/local workspace delivery, allow-root, and post-copy SHA verification tested | offline protocol/replay evidence only; Windows Bambu development excluded |
| Non-slicer geometry backend | dependency-free ASCII/binary STL fixtures verify water-tight edge counting, dimensions, print height, bed contact, downward-face area, volume and COM stability; wall thickness remains unknown | pass offline |
| Geometry L6 recipe | canonical STEP + normalized STL + JSON/Markdown report + relative SHA manifest; unavailable/escaping converter and secret provenance fail closed | pass offline with deterministic converter fixture |
| REST geometry owning wrapper | persisted STEP manifest/SHA is rechecked; disabled module config reports unavailable; configured subprocess fixture builds REST-owned L6; MCP can select only translation ID | pass offline; default production config disabled |
| Generic STEP converter adapter | real subprocess fixture verifies argv/no-shell execution, paths with spaces, pinned version, timeout/exit failure, missing executable, unsupported placeholders, STL parse, triangle count, and Windows `CREATE_NO_WINDOW` | pass offline plus CadQ field run; human confirmed no console window on rerun |
| Active production STEP backend | adjacent CadQ virtualenv: CadQuery 2.8.0 / OCP 7.9.3.1 via Windows `wsl.exe --exec`, 0.05 mm / 5 deg tessellation | pass live-local; committed configs remain disabled by default |
| Dependency reuse and install boundary | bounded explicit→sibling venv→global Python→Windows/WSL scan; preserves venv launcher symlinks; importlib metadata probe; standalone path bootstrap; opaque candidate IDs; re-scan-on-configure; structured `ask_before_install` when empty | pass offline; real WSL sibling CadQ candidate found locally and from Windows REST status; automaticInstall=false |
| Deferred slicer backend | Bambu Studio execution and sliced-metrics parser | excluded until explicitly resumed on an installed/pinned environment |

## Redundancy and contract-integrity follow-up

A complete 104-tool mechanical and semantic audit found no duplicate names,
missing/orphan handlers, same-callable aliases, unreachable tools, or invalid
JSON Schemas. The identical no-argument schemas and the fix/group,
snippet/parameter, browser/REST geometry, and domain-search pairs remain distinct
contracts. L4/L5/L6 composition and project control are intentional layering.

The audit did find contract overlap and metadata drift, which was corrected:

- `browser_delete_tab` is now a default-hidden deprecated exact-name wrapper over
  the same exact data-id deletion core as `browser_delete_element`; partial and
  ambiguous names fail before mutation.
- `browser_draw_part` is default-hidden and rejects empty dimensions before any
  browser action. `browser_drawing_insert_views` owns views-only requests, while
  `browser_draw_part_with_views` requires one or more dimensions.
- Public `browser_create_tab` no longer accepts Drawing, whose pending dialog was
  nonterminal; `browser_create_drawing` owns the completed L4 transaction.
- Browser geometry readiness/configuration/package metadata is offline and does
  not require a browser session; readiness is a boundary observation, not L4.
- Confirmation metadata now distinguishes schema requirement, real-call
  requirement, conditional dry-run confirmation, and eval budget override. Six
  non-dry-run browser cloud mutators require `confirm_mutation` in JSON Schema.
- Persistent local/session effects are explicit in catalog `sideEffects`.
  Screenshot dry-run no longer creates a directory, and filename traversal is
  rejected.
- `onshape_api_quota` is correctly classified as a REST operation rather than a
  documentation/reference tool. Recorder actions are defined and documented in
  one final schema.

The authoritative planned-tool registry was checked again after these fixes and
still contains no unimplemented rows. The audit produced refinements to existing
contracts, not new tool requirements.

## Persisted field evidence

- `dev/button-map/scan-fs-module-outline.json`: symbol inventory and glyph kinds.
- `dev/button-map/scan-fs-editor.json`: context menu, fold commands/widgets,
  Length parameter toolbar item, and source-restoration proof.
- `dev/button-map/scan-app-shell.json`: shell selectors, share dialog,
  notification count, Drawing frame observations, and limitations.
- `dev/button-map/scan-drawing-four-views.png`: raw four-view Drawing canvas.
- `dev/tests/test_browser_planned_tools.py`: focused schema, safety, acceptance,
  pixel, project, and generated-FeatureScript tests.

## Acceptance boundaries

- `browser_read_selection_preview` and notification-drawer selectors were not
  visible in the inspected state. The evidence file labels them unverified and
  the readers return structured absence instead of synthesizing content.
- `browser_view_orientation` can read the cube state and verify a visual state
  change for standard orientation actions; it does not claim a semantic camera
  label unavailable from the DOM.
- Wall thickness is sampled evidence, never a global minimum.
- Browser STEP export: after human login restoration, `PS-PartA-wall` export dialog
  was opened and its stable selectors/options captured. One explicitly approved
  submission then produced `field_export_20260825.step` as a direct, single,
  non-ZIP AP242 millimeter download. The 34,084-byte artifact and persisted browser
  provenance manifest independently recomputed the same SHA-256.
- The accepted browser L6 geometry package used CadQuery 2.8.0 / OCP 7.9.3.1,
  produced a 4,984-byte STL (`a3486ec5…96d`), 98 triangles, watertight=true,
  dimensions 40.0 x 4.7 x 40.0 mm, volume 6,271.107 mm³, and complete non-wall
  geometry metrics. `pass` remains null because no threshold policy is defined;
  wall thickness remains null because that backend is unavailable.
- Print orientation remains `unknown`, but the stronger six-level conclusion is
  that the draft-analysis implementation is not an FDM orientation engine at
  all. It is cataloged `semantically_invalid` and default-hidden pending the
  shared STEP/converter/Bambu replacement.
- Cloud-creating/editing operations still require a separately authorized
  Windows smoke before they can be called field-validated.

## Verification commands

```bash
env -u LIVE_API_ENABLED PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest discover -s dev/tests -v
python3 onshape_docs/verification/verify_docs.py
python3 onshape_docs/scripts/build_tool_reference.py --check
git diff --check
```
