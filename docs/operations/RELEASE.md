# Onshape MCP consumer Release specification

Audience: Production / Operator (primary), Production / User (secondary)

Status: **specification only.** This document defines what a consumer Release
artifact must contain and how an Operator installs, verifies, upgrades, rolls
back, and unregisters it. There is no packaging pipeline, no root packaging
manifest, and no archive in this repository (`docs/development/START.md`). The
machine-checkable form of the whitelist/denylist below is
`dev/tools/consumer_release_spec.py`; the checks are in
`dev/tests/test_consumer_release.py`.

The MCP server version is `1.3.0` (`mcp_main/win/mcp/identity.py`). The `3.0.7`
release and its `sha256:50852ae9…` digest belong to the **development**
governance package (`AGENTS.md`), not to this artifact; the artifact carries no
governance package and requires no `apg` CLI.

## Consumer prerequisites

- Native Windows host with Python >= 3.11 and an **existing** Chrome/Edge.
- **No Git required.** A Release artifact is unpacked, not cloned.
- **No APG required.** The consumer never runs `apg context` and never installs
  the project-governance package (`agent-project-guides/` is denylisted).
- **No WSL required.** The external `win-wsl-mcp-bridge` adapter is optional;
  a native-Windows stdio client can launch the server directly.
- Interactive desktop access only when a human completes Onshape SSO/2FA.

## Artifact contents (whitelist)

Only versioned code and consumer/operator documentation are shipped. Every path
below is whitelisted; anything not listed is not part of the artifact.

| Whitelisted path | Why it is runtime |
|---|---|
| `mcp_main/` | MCP entrypoint, server, tool registry, tool views, runtime policy |
| `mcp_main/dsh/` | Runtime policy companion + DSH registration example (runtime policy/companion) |
| `onshape_browser_mode/` | Browser facade; includes `wheels/` and `requirements-windows.txt` |
| `onshape_rest_api_mode/` | Guarded REST boundary and quota bookkeeping code |
| `onshape_docs/__init__.py`, `onshape_docs/README.md`, `onshape_docs/index.json` | Offline project-doc index the server exposes through `docs_search`/`docs_list`/`docs_section` |
| `onshape_docs/query/` | Offline query code for project docs, FeatureScript, and REST reference |
| `onshape_docs/experience/`, `onshape_docs/guide/` | Authored lookup content served by the offline doc tools |
| `onshape_docs/reference/README.md`, `reference/quick-reference.md`, `reference/index/`, `reference/quick/` | Generated FeatureScript/REST lookup indexes (the runtime subset) |
| `docs/usage/MCP_CONSUMER.md` | Production / User contract |
| `docs/operations/MCP_RUNBOOK.md` | Production / Operator runbook |
| `docs/operations/RELEASE.md` | This document |
| `docs/generated/` | Derived tool reference (`TOOL_REFERENCE.md`) |

`onshape_docs/reference/raw/` **is** in the whitelist and ships with the
artifact: it is the provenance and last-resort full-text layer that the
lookup-first protocol falls back to, and the query tools only expose indexes
over it. Measured: `du -sb onshape_docs/reference/raw` is 10,258,423 bytes
(~9.8 MiB); it is the single largest whitelisted tree. `onshape_docs/scripts/`
and `onshape_docs/verification/` are development/build-plane content and are
not part of the consumer artifact.

`fdm_analysis/` also **is** in the whitelist (224K): its geometry and slicer
capabilities are MCP tools of this server. See the decided section below for the
dependency adjustment that came with that decision. `dev/` and `temp/` are
development-plane content.

## Never bundled, never deleted (denylist)

The artifact must not contain the paths below, and install, upgrade, rollback,
or uninstall must **never delete** them from the host:

- Development governance: `AGENTS.md`, `CLAUDE.md`, `agent-project-guides/`,
  `.agent-guides/`, `.agent-project-guides/`, `.agent-project-guides.json`.
- Development workspace: `dev/`, `.git/`, `.venv/`, `temp/`, `.mnemon/`,
  `__pycache__/`.
- Mutable browser state: `onshape_browser_mode/config/browser-state.json`,
  `onshape_browser_mode/config/browser.local.toml`,
  `onshape_browser_mode/user_data/` (the persistent profile and its owner),
  `onshape_browser_mode/outputs/`.
- Mutable REST state: `onshape_rest_api_mode/config/onshape-credentials.json`,
  `onshape_rest_api_mode/config/onshape-state.json`,
  `onshape_rest_api_mode/config/api-usage.json` (the quota ledger),
  `onshape_rest_api_mode/outputs/`.
- Local view state: `mcp_main/win/mcp/config/tool_views.local.toml`.

Some of these live under whitelisted module directories; the denylist is an
exclusion overlay that always wins. `dev/tools/consumer_release_spec.py` shows
which denylisted candidates currently exist in a checkout and reports them as
excluded.

### Geometry backend selection is machine-local state (resolved 2026-09-26)

`onshape_browser_mode/config/geometry-backend.json` holds the selected geometry
backend — provider, executable, argument template, tolerances — for one host. It
is machine-local state in exactly the sense above, so it is **denylisted**: the
artifact never carries it, and an upgrade never writes or deletes it. It used to
be a tracked file and therefore *inside* the artifact, which meant a plain extract
silently disabled a configured backend: a real host was measured carrying
`enabled: true` / `cadquery-ocp-wsl` while the artifact carried its shipped
`enabled: false` default. `onshape_rest_api_mode/config/geometry-backend.json` is
the same file name in the REST module and is treated with it.

Absence is a supported state, not a broken install. Each mode ships
`geometry-backend.json.example` — the disabled default template — and
`fdm_analysis.configuration.load_command_geometry_config` substitutes that same
in-code default when the live file does not exist, while a file that *exists* but
is malformed still raises (an operator mistake must not be hidden). A fresh
install therefore reports `configFilePresent: false` / `ready: false` from
`onshape_geometry_status` instead of failing, and
`onshape_configure_geometry_backend` creates the live file and its parent
directory on first configuration.

For an upgrade or an in-place refresh, both live paths are state: exclude them
from the copy — the in-place procedure below does — and verify afterwards that the
host's selection is unchanged.

### State preservation rule

The artifact carries **versioned code only**. Configuration and state are owned
by their modules, are respected as-is, and are backed up to an explicit recovery
point before any upgrade, rollback, or uninstall. Upgrade and rollback replace
code and never delete state by default. A profile, credential file, ledger, or
output directory is not "cleanup".

## Versioning and integrity

- A release is named for the MCP server version (`1.3.0` today) plus a release
  revision; it never borrows the governance `3.0.7` version.
- The artifact ships `release-manifest.json`: one entry per file with its
  workspace-relative POSIX path, byte size, and SHA-256.
- A `SHA256SUMS` sidecar carries the per-file digests and the manifest digest, so
  an Operator can verify before install without trusting the archive.
- SHA-256 is computed as in `fdm_analysis/contracts.py:file_sha256` and matches
  the existing bundled-wheel convention in
  `docs/development/BROWSER_COMMON_INTEGRATION.md` (which pins
  `onshape_browser_mode/wheels/lijq_browser_common-0.1.0.dev2-py3-none-any.whl`).
- `onshape_browser_mode/requirements-windows.txt` resolves `./wheels` relative to
  itself; verify the bundled wheel digest before installing.
- That integrity information is **already producible offline, and only that**:

  ```
  python dev/tools/consumer_release_spec.py --check --emit /some/dir/outside/the/checkout
  ```

  writes `release-manifest.json` (per-file path / bytes / SHA-256, the excluded
  paths, and a `planSha256` digest over the ordered rows) and a `SHA256SUMS`
  sidecar in real `sha256sum -c` format — every listed path is relative to the
  checkout root, so verify with
  `cd <checkout> && sha256sum -c <dir>/SHA256SUMS`. It emits nothing when an
  invariant fails, refuses a destination inside the checkout (that would change
  the tree it just described), and the manifest states `artifactStatus:
  "spec-only"` with `artifactFormat: null`: **no artifact is built, compressed,
  signed, or published.**

## Building the artifact

Decided 2026-09-25 (owner: "prepare the release"); format, publication, and
signing are recorded here rather than left implicit, and each remains reversible
by re-running the build with a different choice:

| Decision | Value | Why |
|---|---|---|
| Format | **zip** | The consumer is native Windows with no Git, APG or WSL, so the artifact must be extractable and runnable with what Windows already has. A wheel needs pip and would not carry the offline docs tree; zipapp/PyInstaller add a toolchain and hide the file list the manifest exists to publish |
| Contents | **exactly `consumer_release_spec.plan()`** | One source of truth. The builder never invents a file list, and refuses to build when the spec's own invariants fail |
| Layout | **no wrapper directory** | The archive root IS the install root, so "extract into an empty directory" is the whole install |
| Publication | **local file, handed over out of band** | This repository has no distribution authority or credentials; the builder writes wherever it is told (outside the checkout) and names the file `onshapescript-mcp-<version>-<revision>.zip` |
| Signing | **unsigned** (SHA-256 only) | Code signing needs a certificate, which is a human/host decision. `release-manifest.json` records `"signed": false` so an unsigned artifact cannot be mistaken for a signed one |

```
python dev/tools/build_release.py --out <dir outside the checkout> [--revision <name>]
```

The build is **reproducible**: fixed zip entry timestamps, sorted entries, fixed
compression level, and the same tree gives byte-identical output. The revision
defaults to the git short HEAD (with `-dirty` when the tree is dirty), so the
artifact always names the source it came from. A build writes only outside the
checkout and writes nothing at all when the spec has an invariant violation.

Beside the archive it writes `<artifact>.sha256`, whose digest is over the
**archive itself** — that is what a consumer verifies before extracting.

## Procedures

Each procedure starts by establishing environment, identity, user/data impact,
recovery point, stop conditions, and explicit Operator approval. Back up the
denylisted mutable state listed above before changing anything.

### Install

1. Confirm prerequisites (native Windows, Python >= 3.11, existing Chrome/Edge).
2. Verify the archive before extracting: compare `onshapescript-mcp-<version>-<revision>.zip`
   against its `.sha256` sidecar. Stop on any mismatch.
3. Unpack the artifact to the deployment directory, conventionally
   `C:\MCP\onshapescript`. The archive root is the install root, so extract into an
   empty directory. Do not clone and do not create a Git workspace.
4. Verify the extracted tree against the shipped `SHA256SUMS`
   (`sha256sum -c SHA256SUMS` from the install root) and read
   `release-manifest.json`; stop on any mismatch.
5. Create the venv and install only the module-owned requirements:
   `.\.venv\Scripts\python.exe -m pip install -r onshape_browser_mode\requirements-windows.txt`.
   Verify the bundled wheel digest first.
6. Run the offline self-check (below). It must complete with zero Onshape
   requests.
7. Register the client/adapter (next section), then complete one human SSO/2FA
   login only when browser work is actually needed.

### Upgrade and rollback

Upgrade replaces code and never deletes state by default. `release-manifest.json`
lists `excludedPaths`: that is the preserved state, and it is absent from the
artifact precisely so extracting can never overwrite it.

1. Record the recovery point (the Operator runbook procedure) and stop the server.
2. Extract the new release into a **new** directory, for example
   `C:\MCP\onshapescript-1.3.0-<revision>`; verify it as in install steps 2-4.
3. Carry the preserved state forward by copying the `excludedPaths` that exist in
   the old install into the same relative locations in the new one: the browser
   profile, `browser-state.json`, `browser.local.toml`, the REST credential and
   state files, `api-usage.json`, `tool_views.local.toml`, and the output trees.
   Copying `api-usage.json` is not optional — the annual Onshape quota ledger must
   not be reset by an upgrade.
4. Re-point the client/adapter registration at the new directory and start it.
5. **Rollback** is steps 3-4 in reverse: re-point the registration at the previous
   directory. Keep the previous directory until the new one has served a request,
   and never delete either one as part of rollback.

### In-place code-only refresh (measured 2026-09-26)

The upgrade above extracts into a **new** directory and re-points the
registration, which keeps the old directory as the rollback point. That move is
not always available: re-pointing needs Operator tooling that edits the
registration, and the persistent profile belongs to the old directory while a
detached resident browser holds it open — hundreds of MB, and copying it live is
both slow and inconsistent. The measured alternative replaces versioned code
only, in place:

1. Record the recovery point: back up the mutable state (the denylist above) and
   `tar` every file the refresh will overwrite, with a sha256 list of them.
2. Verify the artifact as in install steps 2-4.
3. Dry-run the copy (`rsync -c -n --itemize-changes`) with every denylisted path
   excluded — the geometry-backend selection included — and assert that the planned
   file set is exactly an allow-list the Operator has reviewed. Any unlisted path
   aborts before a single byte is written.
4. Apply the same command for real. It must carry no `--delete` and must not
   write an excluded path.
5. Re-verify content equality against the extracted artifact, then confirm the
   excluded state files still carry their original mtimes: every file from the
   reproducible archive carries the fixed 1980 archive timestamp, so an unchanged
   2026 mtime proves the artifact did not overwrite it. A live geometry-backend
   selection keeps its 2026 mtime and stays byte-identical through the refresh.
6. Restart the server so children load the new code. Roll back by extracting the
   `tar` from step 1 and restarting again.

A detached resident browser survives this refresh — measured 2026-09-26: the same
browser PID and the same DevTools browser GUID answered before and after two
server restarts — so a code refresh does not cost the human a login.

### Unregister / uninstall

1. Remove the client/adapter registration (and the DSH patch) first, so nothing
   restarts the server mid-removal.
2. Stop the server and confirm no MCP child and no browser process remain.
3. Uninstall deletes **code only**. Do not delete the preserved state unless the
   Operator has explicit user approval, and delete named paths rather than using a
   wildcard. A deleted profile costs a manual SSO/2FA login; a deleted
   `api-usage.json` costs the only local record of consumed Onshape quota.


### DSH register

1. Register the ordinary command with an independently installed
   `win-wsl-mcp-bridge` using id `onshape`, the deployment directory as `cwd`, and
   `multiProcessAllowed=false`.
2. Configure DSH from `mcp_main/dsh/cordis.patch.yml.example`. Install the MCP
   client and the generated runtime-policy companion as one generation.
3. Set `ONSHAPE_MCP_TOOL_EXPOSURE=gateway` in the registration (see Defaults).
4. Verify the model-visible runtime policy, not merely listed tools. The DSH
   client `@deepseek-ai/dsh-mcp-client` >=0.1.0-rc.8 registers tools without
   projecting `initialize.instructions`, which is why the companion is required.
5. Back up the client profile patch/package state before any change.

### Diagnose (redacted export)

1. Collect read-only health evidence first: process identity, initialize
   identity/version, `tools/list`, `browser_session(action=status)`, REST
   quota/state guards, and the loopback-only resident endpoint if enabled.
2. Export a **redacted** diagnostic bundle: server version, config shape,
   `contextClosed`/`playwrightStopped`/`warnings`, and log excerpts. Never export
   credentials, authorization headers, cookies, tokens, or profile contents.
3. Use `mcp_main/win/mcp/config/tool_views.local.toml` plus `tool_views.local.toml.example`
   to explain display differences between deployments.
4. If the deployment itself is broken, use the Operator runbook
   `docs/operations/MCP_RUNBOOK.md`; a consumer-side code defect is filed as a
   development Issue, never patched in the deployed copy.

### Upgrade

1. Approve the target generation and capture the recovery point (code manifest
   plus all mutable state).
2. Stop the client/adapter so the MCP process and its browser exit cleanly.
3. Replace versioned code only. Preserve every denylisted path.
4. Re-run the offline self-check with zero Onshape requests.
5. Start exactly one owner and verify identity, runtime-policy revision, gateway
   display, tools, and logs.
6. Stop on profile-lock ambiguity, credential exposure, quota-guard failure,
   unexpected cloud mutation, or unexpected external exposure.

### Rollback

1. Stop the single owner; never leave two profile owners.
2. Restore the previous code generation from the recovery point and restore the
   preserved mutable state if it changed.
3. Re-run the offline self-check, restart one owner, and verify identity, policy,
   and status. Do not delete profiles or ledgers as cleanup.

### Unregister

1. Remove the DSH registration and the runtime-policy companion entry.
2. Stop the MCP/browser process; confirm no resident browser still owns the
   profile.
3. Remove only installed code if decommissioning. Preserve credentials, ledger,
   profile, `user_data/`, and `outputs/` unless the user explicitly asks to
   delete them.

## Defaults

- Real REST API access is **disabled**: `LIVE_API_ENABLED` must be unset;
  `onshape_rest_api_mode` refuses live calls without it.
- The **install self-check completes with ZERO Onshape requests**: start the
  server, complete one `initialize`/`tools/list` exchange against the local
  process, and confirm identity and the runtime-policy revision. Nothing in the
  artifact may contact Onshape during install or self-check.
- Default tool display is **`gateway`**, and that is now the in-repo code fallback
  too: with no explicit argument, no `ONSHAPE_MCP_TOOL_EXPOSURE`, and no
  `tool_views.local.toml`, `mcp_main/win/mcp/tool_views.py` starts a connection in
  `gateway`. Precedence is an explicit argument, then `ONSHAPE_MCP_TOOL_EXPOSURE`,
  then `mcp_main/win/mcp/config/tool_views.local.toml [exposure].mode`, then
  `gateway`; pinning `ONSHAPE_MCP_TOOL_EXPOSURE=gateway` in the registration is
  therefore an explicit statement of intent, not a correction of the default.
  `dynamic` collapse/expand is a separate, orthogonal control.
- **No implicit download** of a large browser or geometry backend. The browser
  layer uses the machine's existing Chrome/Edge; a geometry backend is
  configured explicitly by opaque candidate id and `ask_before_install` always
  asks the human first.

## Optional browser layer

The browser layer is optional. The MCP server still runs and serves its offline
tools without Playwright: `onshape_browser_mode/session.py:1-6` states that
"offline tools need neither Playwright nor browser_common installed", and a
browser tool started without Playwright raises `PlaywrightNotInstalled` with the
exact install command (`session.py:521-526`). Corroborating operating experience
is in `onshape_docs/experience/browser-automation.md`. Do not install a browser
merely to satisfy the artifact; install the browser dependency only when
browser work is actually requested.

## Open decisions (not yet specified)

These are **undecided**, not silently assumed:

1. **Publication location and distribution channel**: where the built artifact is
   stored and how it reaches a consumer host. The builder writes a local file and
   nothing else; nothing is uploaded.
2. **Code signing**: whether the artifact and/or manifest is signed. Today's
   artifact is unsigned and says so.
3. **The native-Windows acceptance run** on a clean consumer environment (see the
   acceptance section above). The offline proxy is automated — the built archive
   is extracted and the server is started over stdio from that directory with
   `PYTHONPATH` removed (`dev/tests/test_release_artifact.py`) — but that is not
   the same as a clean Windows host.

Decided and no longer open: **artifact format (zip)** and **contents** (the
whitelist), both recorded in the build section above. No path is pending a
membership decision: `PENDING_DECISION` in `dev/tools/consumer_release_spec.py`
is empty.

## Decided: `fdm_analysis/` ships, and the dependency shape was adjusted

**DECIDED (owner, 2026-09-25): `fdm_analysis/` is part of the artifact.** The
geometry and FDM capabilities are exposed as MCP tools of this server
(`onshape_geometry_status`, `onshape_build_geometry_package`, the slicer-backed
pipeline, …), so the package belongs to this tool set rather than being an outside
concern. It is whitelisted; measured at 224K.

What was adjusted instead of the file list is the **dependency shape**. The
original defect was not that the package existed but *when* it was reached:

| Before | After |
|---|---|
| `mcp_main/win/mcp/server.py` imported `onshape_rest_api_mode.geometry` and `step_export` at module scope, so importing the server failed without `fdm_analysis` and pulled 16 submodules with it | those imports moved into the four handlers that use them, next to every other lazy `onshape_*` import in that file; importing the server now loads **0** `fdm_analysis` submodules |
| `fdm_analysis/__init__.py` re-exported eagerly, so `from fdm_analysis.contracts import file_sha256` — the one symbol the Onshape STEP export needs — loaded 16 submodules including `slicers/bambu_studio` and `slicers/execution` | PEP 562 lazy re-exports: the same import loads **1** submodule (`fdm_analysis.contracts`) |

Both numbers are pinned by `dev/tests/test_import_shape.py`, which measures them in
a fresh interpreter (in-process assertions would be masked by siblings that import
the package eagerly). The public names and `__all__` are unchanged, so no caller or
test needed rewriting.

Two consequences worth keeping:

- Removing `fdm_analysis/` from the whitelist is **not** a slim-down; it makes the
  server unimportable. `dev/tests/test_consumer_release.py` pins the decision.
- A future module-scope import of the geometry/step_export chain reintroduces the
  old coupling. Add the import inside the handler instead.

## Related documents

- `docs/operations/MCP_RUNBOOK.md` — deployed-process ownership, health, restart,
  recovery.
- `docs/usage/MCP_CONSUMER.md` — Production / User calling contract.
- `docs/development/START.md` — development commands; states there is no root
  packaging manifest.
- `docs/development/BROWSER_COMMON_INTEGRATION.md` — pinned wheel and its SHA-256
  convention.
- `dev/tools/consumer_release_spec.py` — the machine-checkable whitelist/denylist,
  `plan()`, `validate()`, and `--check`.
