# Shared FDM analysis library

`fdm_analysis` is a transport-independent local library. It is deliberately
separate from `onshape_browser_mode` and `onshape_rest_api_mode`:

- browser mode owns browser STEP export and download evidence;
- REST mode owns asynchronous STEP export, quota, polling, and download;
- both modes convert the resulting file into the same `StepArtifact` contract;
- this package owns STEP tessellation interfaces, mesh-analysis interfaces,
  slicer interfaces, reports, and L6 package manifests.

The package registers no MCP tools and performs no Onshape REST request.

## Current status

**Windows Bambu exclusion:** the current computer does not have Bambu Studio.
Non-Bambu STEP, geometry, report/manifest, source-adapter, and exchange work may
continue, but this package is not a working slicer integration. Existing Bambu
command/execution code is protocol/replay infrastructure only and must not be
presented as installed or field-validated.

Implemented offline infrastructure:

- canonical STEP, normalized mesh, profile, and sliced-project contracts;
- explicit `StepConverter`, `GeometryAnalyzer`, and `SlicerBackend` protocols;
- pinned argv-only `CommandStepConverter` adapter with no shell, bounded timeout,
  exit-code handling, non-empty STL parsing, triangle count, tolerance provenance,
  and Windows `CREATE_NO_WINDOW` execution;
- `cadquery_step_to_stl.py` field-validated against the adjacent CadQ environment
  (CadQuery 2.8.0 / OCP 7.9.3.1), including deterministic Windows-to-WSL path
  mapping. Committed owning-mode configs remain disabled by default; the Windows
  field deployment selects this backend through `wsl.exe --exec`;
- bounded reusable dependency discovery in sibling project virtual environments,
  global Python environments, and the Windows/WSL counterpart. Results expose
  versioned opaque candidate IDs rather than paths; configure re-scans before
  writing, and no-match results require an agent to ask before any installation;
- fail-closed unavailable converter/analyzer placeholders;
- Bambu Studio CLI command construction for documented STL/3MF input;
- Windows-native, WSL-to-Windows interop, and offline-replay execution adapters;
- report and manifest generation with artifact SHA values;
- dependency-free ASCII/binary STL geometry analysis for watertightness, bounds,
  print height, bed contact, downward-face area, volume, and center-of-mass
  stability; wall thickness remains explicitly unknown;
- non-slicer `build_geometry_package` L6 recipe containing canonical STEP,
  normalized STL, JSON/Markdown reports, relative artifact paths, SHA values,
  backend provenance, and threshold-free acceptance;
- browser and REST source adapters that produce the same STEP contract;
- browser-owned `browser_export_step` using live-observed dialog selectors,
  explicit URL-ID acceptance, AP242 millimeter direct-download configuration,
  non-ZIP STEP acceptance, and persisted browser provenance manifest;
- browser-owned `browser_geometry_status` and `browser_build_geometry_package`
  using disabled-by-default browser module converter configuration;
- REST-owned `onshape_export_step` with a bounded asynchronous dry-run/replay
  contract, resumable translation IDs, no implicit polling retry, module-owned
  staging, and persisted `step-manifest.json`;
- REST-owned `onshape_geometry_status` and `onshape_build_geometry_package`
  wrappers using only module-owned converter configuration. The default config is
  disabled and actual execution fails closed until an operator selects a pinned
  executable.

Optional future non-Bambu work:

- add a validated wall-thickness backend instead of reporting unknown;
- field-validate REST STEP acquisition only if a separately approved live REST
  request is justified. The current REST transport remains mock/replay verified to
  preserve the zero-REST regression boundary.

Deferred by explicit scope: the version-bound Bambu Studio metrics parser,
production slicer integration, and slicer-owning MCP tools.

## Windows and WSL execution

The field-validated non-Bambu converter runs `C:\Windows\System32\wsl.exe`
with fixed argv to the adjacent CadQ Python environment. The CLI maps Windows
staging paths to `/mnt/<drive>` deterministically, and `CommandStepConverter`
sets Windows `CREATE_NO_WINDOW`; a human-observed rerun confirmed that no console
window appeared.

Bambu Studio is a Windows application. Production browser/REST tools normally
run inside the persistent Windows MCP Engine and use `NativeWindowsExecution`.

Direct WSL use is supported through `WslWindowsExecution` only when every
executable/input/profile/output path lives under `/mnt/<drive>/...`. The adapter
invokes the Windows executable through WSL interop and converts artifact
arguments to `C:\...` style paths. It rejects `/home/...` paths because the
Windows process cannot safely share the same artifact contract there.

`ReplayExecution` exists only for offline fixtures. Its metadata explicitly says
`production: false`; it must not be used as evidence that Bambu Studio is
installed or functional.

## Artifact exchange back to the agent workspace

The agent workspace normally lives under WSL `/home/...`; Bambu Studio must not
consume that path directly. The package therefore uses two phases:

1. Windows Engine performs STEP conversion, analysis, and slicing in a Windows
   local staging directory.
2. After `manifest.json` is complete, `WindowsToWslDelivery` maps the configured
   WSL destination to `\\wsl.localhost\\<distro>\\...`, copies the whole package,
   and re-verifies every manifest artifact's byte count and SHA.

When the library is invoked directly from WSL, `WslLocalDelivery` copies from the
`/mnt/<drive>` staging directory into the WSL workspace and applies the same
verification. Manifest artifact paths are relative, so Windows staging paths do
not leak into final workspace paths.

`WorkspaceDeliveryTarget.allowed_workspace_root` is a configured boundary, not a
caller-granted permission. Destinations outside that root, traversal paths,
existing output directories, invalid distro names, missing artifacts, and SHA
mismatches fail closed.

## FDM conclusion boundary

A package can be structurally complete while its FDM assessment remains
`unknown`. The report requires both geometry and slicer metrics. Even when all
metrics exist, `pass` stays `null` until a reviewed printer/material/process
threshold policy exists. Persisting files is not sufficient evidence of
printability.
