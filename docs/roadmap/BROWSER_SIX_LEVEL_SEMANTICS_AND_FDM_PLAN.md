# Browser six-level semantics and FDM delivery plan

Status: implemented for the active non-Bambu scope; six-level semantic exposure,
FDM fail-closed correction, Project schema v2, shared contracts, browser/REST STEP
and geometry owning tools, workspace exchange, browser STEP field export, and a
CadQuery/OCP geometry backend are verified. Windows Bambu remains deferred.

Date: 2026-08-25

This plan refines the existing optional L1-L4 browser semantics into an optional
six-level discovery convention and separates deliverables from project control.
It also corrects the current FDM tooling boundary: Onshape draft analysis is not
an FDM print-orientation analysis, STEP is the canonical exported model, and the
shared FDM analysis implementation belongs outside both browser and REST modes.

This document originally proposed the migration and now tracks its staged
implementation. The optional six-level catalog, default exposure helper,
consumer guidance, FDM fail-closed correction, and project schema v2 are
implemented. Semantic MCP exposure with fixed discovery/invocation gateways, the
shared FDM contract library, browser/REST source adapters, and verified
Windows/WSL workspace exchange are also implemented. Browser STEP download and
non-Bambu geometry were field-validated with the adjacent CadQuery 2.8.0 / OCP
7.9.3.1 backend. Windows Bambu Studio integration remains explicitly deferred.
Semantic levels remain optional discovery and guidance metadata rather than
registration or execution constraints.

## 0. Windows Bambu exclusion

Development has resumed for six-level exposure, Project/L6, STEP transport,
non-Bambu geometry analysis, workspace exchange, and their offline-first
browser/REST wrappers. The current computer does not have Bambu Studio, so all
Windows Bambu work remains excluded.

While this exclusion is active:

- do not probe, invoke, install, or develop against Bambu Studio;
- do not implement a Bambu metrics parser or describe slicing as available;
- keep Bambu execution adapters as unverified protocol/replay infrastructure;
- keep `browser_print_orientation_check` and `browser_print_optimize_part`
  fail-closed/default-hidden rather than restoring draft analysis;
- make no live REST request for this work.

Bambu work resumes only after the user installs and pins a version, supplies
non-secret printer/process/filament profiles, and explicitly includes Bambu in
the development scope. Capability probing and versioned fixture capture must
precede any public slicer tool; offline mock success is not field evidence.

## 1. Goals

1. Distinguish generic browser primitives from generic browser transaction
   flows.
2. Distinguish partial Onshape UI interactions from completed and verified
   Onshape domain transactions.
3. Distinguish multi-transaction workflows from independently consumable
   deliverables.
4. Permit same-level composition without treating call depth as semantic level.
5. Define a project as a DAG containing one or more deliverables instead of
   treating the project runner itself as a deliverable level.
6. Hide context-expensive L1 and L3 tools from ordinary discovery while keeping
   them explicitly discoverable for development, diagnostics, recovery, and
   future human assistance.
7. Remove draft analysis from the FDM conclusion chain.
8. Share STEP conversion, mesh analysis, Bambu Studio slicing, reports, and
   manifests across browser and REST source adapters.
9. Preserve zero-REST browser development and offline regression by default.

## 2. Non-goals

- Semantic levels do not grant credentials, mutation authority, or REST budget.
- Missing semantic metadata does not prevent a tool from registering or running.
- This plan does not dynamically remove tools from the authoritative handler
  registry.
- This plan does not claim that the current Bambu Studio CLI supports STEP input.
- Production STEP tessellation is provider-configured and disabled by default;
  field validation selected the adjacent CadQuery/OCP backend without making that
  machine-specific path part of the committed default.
- This plan does not make a transient screenshot or arbitrary output file an L6
  deliverable merely because it is persisted.

## 3. Six semantic levels

| Level | Stable name | Contract | Typical result |
|---|---|---|---|
| L1 | browser_primitive | One generic browser mechanism with no Onshape domain semantics | click, key press, wait, DOM read, screenshot |
| L2 | browser_transaction | A composite generic browser flow with a terminal generic postcondition and no Onshape domain semantics | fill and submit a generic form, choose an exact menu item and verify a generic count change |
| L3 | onshape_interaction | An Onshape-aware UI interaction that prepares, inspects, or recovers a domain operation but does not claim the completed domain transaction | open Extrude, select entities, fill depth, inspect or cancel a pending dialog |
| L4 | onshape_transaction | One completed and verified Onshape domain mutation or one complete Onshape domain observation | create one Extrude feature, insert one custom feature, add one drawing dimension, analyze one explicit FDM orientation |
| L5 | onshape_workflow | Multiple independent L4 transactions or observations composed into one goal without an independently consumable deliverable contract | deploy/version/apply FeatureScript, rank several FDM orientations, perform a transient full feasibility analysis |
| L6 | deliverable_recipe | One independently consumable remote or local result with final acceptance, artifact manifest, provenance, and a retry/resume boundary | complete Part Studio, Assembly, detailed Drawing, or FDM STEP/STL/3MF/report package |

The stable name must accompany the numeric level in authored documentation and
catalog results. Numeric labels alone are too easy to misread during migration.

## 4. Atomicity and composition

Semantic level is determined by the public contract, not by the number of
internal function calls.

### 4.1 Browser atomicity

L1 may internally emit several trusted events when those events implement one
browser mechanism. L2 may compose multiple L1 mechanisms while remaining fully
domain-agnostic.

A generic sequence such as locate, clear, type, press Enter, and wait for a URL
condition is L2 if its public inputs and outcomes contain no Onshape concepts.
The same number of actions becomes at least L3 when the contract names an
Onshape feature dialog, Part Studio selection, Drawing view, or other Onshape
state.

### 4.2 Onshape atomicity

L4 atomicity is defined by the primary Onshape domain commit or complete domain
question, not by geometric complexity.

- One accepted Extrude history node is one L4 transaction.
- One accepted custom FeatureScript history node may remain one L4 transaction
  even if that feature creates many bodies.
- Deploying FeatureScript and inserting the custom feature are two independent
  commits; their parent is at least L5.
- A complete read-only question, such as evaluating one explicit FDM
  orientation, may be L4 without a mutation.

### 4.3 Same-level composition

Same-level composition is allowed and must be acyclic.

- L1 may use L1 helpers.
- L2 may use L2 generic flows while the result remains domain-agnostic.
- L3 may use L3 interactions while they belong to the same pending Onshape
  transaction or recovery context.
- L4 may use same-level aliases, guards, and verification reads when the parent
  still has one primary domain commit or one complete domain question. Two
  independent primary commits promote the parent to L5.
- L5 may use L5 subworkflows while no deliverable contract is closed.
- L6 may aggregate L6 child deliverables while preserving every child manifest,
  acceptance result, and recovery boundary.

The level of a parent is not `max(child level) + 1`. Promotion occurs only when
the parent's public contract crosses a semantic boundary.

Lower-level code must not depend on a higher-level operation. This direction is
an architecture convention and lint target, not a runtime permission system.

## 5. Project control plane

`browser_run_project` and equivalent runners belong to a separate project
control plane, not to L6.

A project is a directed acyclic graph containing one or more L6 deliverable
nodes. Examples:

- a small project may contain one complete Part Studio L6;
- a multi-part product may contain several Part Studio L6 nodes, one Assembly L6
  node, and one or more Drawing L6 nodes;
- a print release may depend on a model L6 and produce an FDM package L6.

A future project schema must retain each L6 node's own checkpoint, manifest,
assertions, and source fingerprint. Project-level assertions aggregate child
outcomes but do not replace child acceptance.

## 6. Discovery and exposure policy

Semantic levels are optional discovery metadata. They do not remove tools from
the authoritative registry and do not add execution authority.

### 6.1 Ordinary discovery

Normal Onshape guidance should prefer stable terminal-state operations:

1. use L6 when the request explicitly asks for an independently consumable
   deliverable;
2. use L5 for a multi-transaction goal without an L6 recipe;
3. prefer L4 over decomposing the operation into L3 interactions;
4. use L2 when a domain-specific transaction is unavailable and a generic
   browser transaction is sufficient;
5. do not automatically decompose L2 into L1 primitives.

For the common non-deliverable path, consumer guidance must explicitly state:
"prefer L5, then L4, then L2, then L6; query L3 or L1 only when their lower-level behavior is
actually required."

### 6.2 L1 and L3 visibility

L1 and L3 are hidden from ordinary discovery to reduce normal schema and context
cost. They remain documented and explicitly discoverable:

```json
{
  "module": "browser",
  "query": "inspect the current pending Extrude dialog",
  "semantic_level": ["L3"],
  "limit": 8
}
```

An explicit `semantic_level=L1` or `semantic_level=L3` is sufficient. No
mandatory `intent` parameter is added: semantic classification is a convention,
not an AI-discipline or permission gate.

The guidance documentation must describe L1 and L3, their use cases, and the
explicit query syntax so that default-hidden tools do not become orphaned
capabilities.

### 6.3 L3 interaction contract

L3 is primarily an internal interaction library for L4. It is also useful for
exception recovery, development diagnostics, and future human assistance.

Where an L3 interaction leaves a pending UI state, its result should describe:

```json
{
  "interactionPrepared": true,
  "pendingCommit": true,
  "uiStateToken": "opaque token",
  "dialogKind": "extrude",
  "expiresOn": ["tab-change", "dialog-close", "page-reload"],
  "allowedNext": ["inspect", "commit", "cancel"]
}
```

L3 must not claim `featureCreated`, `drawingCompleted`, or similar domain
success. L4 owns commit/cancel completion and domain readback.

These fields are a semantic contract for classified L3 tools. They are not a
new authorization mechanism.

## 7. Proposed catalog metadata

A future catalog entry may include:

```json
{
  "semanticLevel": "L4",
  "semanticName": "onshape_transaction",
  "compositionKind": "composite",
  "terminalState": true,
  "defaultExposure": true,
  "explicitLevelRequired": false,
  "dependencies": ["internal:onshape_interaction.extrude"],
  "primaryEffect": "create_extrude_feature",
  "outcomeKey": "featureCreated",
  "deliverableTypes": []
}
```

L1 and L3 normally use `defaultExposure=false` and
`explicitLevelRequired=true`. Unclassified tools remain valid and simply do not
participate in level filtering or automatic semantic routing.

Catalog validation is an offline lint/documentation check. It must not reject a
tool registration solely because semantic metadata is missing.

## 8. Initial migration examples

| Current capability | Proposed level | Reason |
|---|---|---|
| `browser_click`, `browser_press_key`, `browser_wait` | L1 | generic mechanisms |
| generic fill/submit or menu/count transaction | L2 | generic terminal browser flow |
| open and populate one Onshape feature dialog without accepting | L3 | pending Onshape interaction |
| create one Extrude, Fillet, custom feature, or Drawing dimension | L4 | one verified Onshape domain transaction |
| `browser_insert_custom_feature` | L4 | one accepted custom-feature history node when prerequisites already exist |
| `browser_deploy_and_apply_featurescript` | L5 | deploy, version, insert, and verify are independent domain transactions |
| `browser_draw_part_with_views` | L5 unless a complete Drawing deliverable contract is added | multi-transaction Drawing workflow |
| design-specific complete Part Studio recipe | L6 | independently usable remote artifact with acceptance and manifest |
| complete detailed Drawing plus export | L6 | independently consumable Drawing artifact |
| `browser_run_project` | project control plane | executes one or more L6 nodes |

The full registry migration is a later implementation phase and requires a
reviewed mapping rather than an automatic numeric shift.

## 9. FDM semantic correction

### 9.1 Draft analysis is not FDM orientation analysis

Onshape draft analysis is a manufacturing-angle visualization. It does not by
itself evaluate FDM bed contact, support demand, bridges, center-of-mass
stability, print height, layer-direction strength, printer build volume, or
profile-specific slicing results.

The current print-orientation implementation must stop using draft analysis as
its FDM conclusion source. A draft-angle observation may remain a separately
named manufacturing proxy, but it must not return FDM pass/fail or orientation
recommendations.

### 9.2 Proposed FDM levels

| Capability | Proposed level |
|---|---|
| export one Part Studio STEP artifact through browser or REST | L4 in the owning mode |
| evaluate one explicit FDM orientation from a converted mesh | shared library operation, not an MCP semantic tool by itself |
| owning-mode wrapper for one complete orientation question | L4 |
| rank several candidate orientations | L5 |
| transient full FDM feasibility analysis | L5 |
| produce STEP, mesh, sliced project, reports, and manifest | L6 |

The existing `browser_print_optimize_part` is not L6. Its current ordering is
also unsafe: it may apply a blend before discovering that orientation is not
assessable. Analysis and mutation must be separated. Any geometry optimization
must have an explicit dry run, confirmation, idempotency guard, and post-change
re-export/reanalysis.

## 10. Shared FDM library boundary

Create a future root-level package alongside the Onshape source modes:

```text
fdm_analysis/
  contracts.py
  pipeline.py
  reports.py
  manifests.py
  conversion/
    base.py
    <selected STEP backend>.py
  slicers/
    base.py
    bambu_studio.py
  metrics/
    geometry.py
    orientation.py
    wall_thickness.py
```

`fdm_analysis` is a reusable local library, not an MCP tool surface. It does not
know Onshape document/workspace/element IDs, browser pages, REST credentials, or
quota. Browser and REST modes each own their source acquisition and expose their
own semantic wrappers around the same library.

The shared input contract is a local canonical STEP artifact plus opaque source
provenance:

```json
{
  "path": "model.step",
  "mediaType": "model/step",
  "sha256": "...",
  "units": "from-step",
  "source": {
    "mode": "browser-or-rest",
    "reference": "opaque mode-owned value"
  }
}
```

## 11. STEP conversion and Bambu Studio

STEP is the canonical exported and delivered CAD model. It must be tessellated
before mesh analysis and Bambu Studio slicing.

The official Bambu Studio CLI documentation currently lists 3MF and STL inputs
and documents `--orient`, `--slice`, `--export-3mf`, `--export-slicedata`,
`--info`, `--load-settings`, and `--load-filaments`. It does not document STEP as
a stable headless input. The plan must therefore include an explicit STEP
converter interface and must not assume GUI STEP support is a stable CLI API.

```python
class StepConverter:
    def inspect_capabilities(self): ...
    def convert(self, step_artifact, tessellation_options): ...
```

Converter output records units, triangle count, linear/angular tolerance,
backend name, backend version, and SHA. Conversion parameters are provenance
because they can change FDM results.

The first production backend remains an open decision:

1. Python OCCT/OCP;
2. external `FreeCADCmd`;
3. a version-pinned Bambu STEP capability only after an offline capability probe
   and persistent fixture prove it;
4. interface plus mock first, with real analysis remaining dependency-missing.

Bambu Studio is wrapped as a replaceable slicer provider rather than treated as
a stable JSON service API:

```python
class SlicerBackend:
    def inspect_capabilities(self): ...
    def slice(self, mesh_artifact, slice_profile): ...
```

The adapter owns executable/version detection, complete printer/process/filament
profiles, bounded subprocess execution, output 3MF/slicedata verification, and
version-bound parsing. Undocumented output fields remain `unknown` until a
fixture verifies them.

Because Bambu Studio is supplied as a Windows application, execution is
explicitly dual-host:

- the persistent Windows MCP Engine uses a native Windows execution adapter;
- direct WSL use invokes the Windows executable through WSL interop and accepts
  only artifacts/profiles/outputs under `/mnt/<drive>/...`, converting arguments
  to Windows paths;
- an offline replay adapter exists for fixtures and is marked non-production.

Both execution paths share the same Bambu command specification and manifest
metadata. Arbitrary WSL `/home/...` paths are rejected instead of being passed to
the Windows process.

Final delivery uses a separate verified exchange boundary. The Windows Engine
builds the package in Windows-local staging, then maps the configured WSL
workspace to `\\wsl.localhost\\<distro>\\...`, copies the package, and rechecks
manifest byte counts and SHA values. Direct WSL use copies from `/mnt/<drive>`
staging into the WSL workspace with the same verifier. Manifest artifact paths
are relative so Windows staging paths do not become final workspace paths. The
allowed WSL workspace root is configuration-owned and cannot be expanded by a
tool argument.

## 12. Browser and REST source adapters

Browser flow, zero REST quota:

```text
browser export STEP
  -> verify download and SHA
  -> call shared FDM library
  -> return browser-owned L5/L6 result
```

REST flow, quota-bearing:

```text
POST asynchronous Part Studio STEP export
  -> bounded translation-status handling
  -> download STEP
  -> call shared FDM library
  -> return REST-owned L5/L6 result
```

The REST adapter must use the vendored endpoint contract, local request builders,
mock/replay, explicit live enablement, and a hard request budget. No live REST
call is needed to implement or test the shared library.

## 13. L6 FDM package contract

A complete package is expected to contain at least:

```text
model.step
model.stl or another normalized mesh
sliced-project.3mf
report.json
report.md
manifest.json
```

The manifest records:

- SHA and media type for every artifact;
- source provenance supplied by the owning mode;
- STEP converter and tessellation settings;
- Bambu Studio version;
- printer, process, and filament profile SHA values;
- orientation transforms;
- supported, failed, and unknown metrics;
- final assertions and warnings;
- checkpoint/resume identity.

FDM feasibility is profile-specific. No tool may claim absolute printability
without recording printer, nozzle, material, process profile, and all unknown
checks.

## 14. Implementation sequence

### Phase 0: plan only — completed

- Commit this authored plan as proposed behavior.
- Make no runtime, schema, registry, or existing semantics changes.

### Phase 1: six-level semantics and guidance — implemented

- Replace the authored four-level definition with the six-level convention.
- Keep level metadata optional and non-authorizing.
- Document default-hidden L1/L3 and explicit discovery.
- Update consumer guidance to rank L5, L4, L2, then L6 for ordinary discovery.
- Move the project runner to the project control plane conceptually.
- Add reviewed migration tables for current browser tools.

### Phase 2: catalog and discovery metadata — implemented

- Keep the complete authoritative registry/handlers intact.
- Default `tools/list` to fixed semantic exposure; retain static compatibility
  and add fixed profile plus opt-in per-connection dynamic modes.
- Expose bounded `browser_discover_tools` and `browser_invoke_discovered` so L1/L3
  schemas load only after an explicit level query.
- Add offline catalog lint for known entries, dependency direction, and cycles.
- Do not reject unclassified or currently unexposed known-name tools; exposure is
  a convention and never execution authority.
- Dynamic mode sends `notifications/tools/list_changed` after effective
  `mcp_tool_view` changes and resets view state on reconnect.

### Phase 3: FDM shared contracts and non-slicer geometry — implemented; wall thickness remains unknown

- Added shared contracts, provider interfaces, reports, manifests, deterministic
  fixtures, and verified artifact exchange.
- Added a dependency-free ASCII/binary STL geometry backend for watertightness,
  bounds, print height, bed contact, downward-face area, volume, and center-of-mass
  stability. Wall thickness remains explicitly unknown.
- Added a non-slicer L6 geometry package recipe with STEP/STL/report artifacts,
  relative manifest paths, SHA verification, backend provenance, and no threshold
  pass/fail invention.
- Added a pinned argv-only converter adapter with no shell, bounded timeout,
  Windows `CREATE_NO_WINDOW`, exit-code and parsed-STL acceptance, and recorded
  tessellation tolerances.
- Reused and field-validated the adjacent CadQ environment: CadQuery 2.8.0 / OCP
  7.9.3.1 imports the real browser STEP and exports a 98-triangle watertight STL.
  The Windows owning mode invokes it through fixed `wsl.exe --exec` argv while
  committed configs remain disabled by default.
- Added bounded dependency reuse: explicit config first, then sibling project
  virtual environments, global Python, and the Windows/WSL counterpart. Public
  status returns opaque versioned candidates, configure re-scans before writing,
  and no-match results require the agent to ask before installation. No automatic
  installation or caller-supplied executable/argv is allowed.
- Keep the existing Bambu command/replay protocol frozen and excluded until the
  user explicitly resumes it on an installed environment.

### Phase 4: source adapters — REST and browser owning wrappers implemented

- REST: implemented `onshape_export_step` with exact AP242 millimeter request,
  bounded no-retry polling, resumable translation IDs, single external-data
  acceptance, module-owned staging, persisted STEP manifest, shared
  `StepArtifact`, dry-run, quota cost, and replay tests. No live request was made.
- REST: implemented offline `onshape_geometry_status` and
  `onshape_build_geometry_package`; converter executable/version/argv comes only
  from disabled-by-default module configuration, while MCP arguments select only
  a verified staged translation ID.
- Browser: login-restored field inspection captured the export dialog selectors
  and option sets. Implemented `browser_export_step` with explicit source URL-ID
  acceptance, STEP/AP242/Millimeter/direct-download settings, non-ZIP STEP
  acceptance, and persisted browser provenance manifest. Dialog open/cancel was
  field-observed; submit/download remains offline-tested until separately approved.
- Browser: implemented offline `browser_geometry_status` and
  `browser_build_geometry_package`; they use browser-owned module configuration
  and accept only a verified export ID.
- Preserve zero-REST and mutation metadata per source mode.

### Phase 5: field validation

- Browser STEP export field acceptance passed after explicit approval: one direct
  AP242 millimeter `.step` download, non-ZIP, 34,084 bytes, persisted SHA verified.
- Non-Bambu converter/geometry field acceptance passed by reusing CadQuery 2.8.0 /
  OCP 7.9.3.1: 98-triangle watertight STL and independently accepted L6 package.
  Windows rerun uses `CREATE_NO_WINDOW`; human observation confirmed no console.
- Keep all Windows Bambu probing, slicing, and metrics validation deferred.
- Keep `LIVE_API_ENABLED` unset unless a separately approved REST-only fact
  cannot be established offline.

## 15. Verification requirements

- Offline semantic catalog and discovery tests.
- Same-level composition and cycle fixtures.
- L3 explicit-discovery tests and ordinary-context exclusion tests.
- Project fixtures containing one and multiple L6 nodes.
- Deterministic STEP-converter mock fixtures.
- Bounded REST STEP POST/poll/download plans, resumable replay, and disabled GET
  retry tests.
- Non-Bambu geometry manifest SHA/provenance/unknown-metric tests.
- No Bambu acceptance criterion while its explicit exclusion is active.
- Browser and REST adapters must produce equivalent shared input contracts.
- Full test discovery with `LIVE_API_ENABLED` unset.
- Generated tool reference and project docs index rebuild after implementation.
- Final roadmap rescan for stale four-level definitions.

## 16. Completion criteria

This plan is implemented only when:

- the six stable level names and optional-metadata rule are consistent across
  authored documentation and catalog output;
- ordinary discovery omits L1/L3 while explicit level queries reveal and
  document them;
- current browser tools have reviewed classifications rather than a blind
  numeric shift;
- the project runner is described and tested as a control plane over one or more
  L6 deliverables;
- no FDM conclusion uses draft analysis as its orientation engine;
- browser and REST source adapters can produce the same canonical STEP artifact
  contract;
- the shared FDM library is independent of both source modes;
- STEP conversion and Bambu Studio capabilities are explicit, versioned, and
  fixture-backed;
- an L6 FDM package contains verified artifacts, reports, manifest, provenance,
  and unknown-state disclosure;
- full offline regression passes with zero Onshape REST requests.

## 17. References

- Current optional four-level and discovery roadmap:
  `docs/roadmap/DYNAMIC_TOOL_DISCOVERY.md`.
- Bambu Studio official command-line manual:
  <https://raw.githubusercontent.com/wiki/bambulab/BambuStudio/Command-Line-Usage.md>.
- Onshape asynchronous Part Studio export guide:
  <https://onshape-public.github.io/docs/api-adv/translation/#export-a-part-studio-to-gltf-obj-solidworks-or-step>.
- Vendored REST operation used by the future API adapter:
  `POST /partstudios/d/{did}/{wv}/{wvid}/e/{eid}/export/step`
  (`createPartStudioExportStep`).
