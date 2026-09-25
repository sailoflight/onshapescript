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

## Procedures

Each procedure starts by establishing environment, identity, user/data impact,
recovery point, stop conditions, and explicit Operator approval. Back up the
denylisted mutable state listed above before changing anything.

### Install

1. Confirm prerequisites (native Windows, Python >= 3.11, existing Chrome/Edge).
2. Unpack the artifact to the deployment directory, conventionally
   `C:\MCP\onshapescript`. Do not clone and do not create a Git workspace.
3. Verify `SHA256SUMS` and `release-manifest.json` against the artifact; stop on
   any mismatch.
4. Create the venv and install only the module-owned requirements:
   `.\.venv\Scripts\python.exe -m pip install -r onshape_browser_mode\requirements-windows.txt`.
   Verify the bundled wheel digest first.
5. Run the offline self-check (below). It must complete with zero Onshape
   requests.
6. Register the client/adapter (next section), then complete one human SSO/2FA
   login only when browser work is actually needed.

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

These are **undecided**, not silently assumed. A human must choose before a
packaging pipeline is written:

1. **Artifact format**: zip vs wheel vs zipapp vs PyInstaller.
2. **Publication location**: where the artifact is stored and distributed.
3. **Code signing**: whether the artifact and/or manifest is signed.
4. **`fdm_analysis/`**: consumer runtime or development-only. It is currently
   neither whitelisted nor denylisted and is reported under pending decisions.

   Blocking evidence (verified, 2026-08): excluding it is **not** a
   ready-to-apply option. `mcp_main/win/mcp/server.py` imports
   `onshape_rest_api_mode.geometry`, which does
   `from fdm_analysis import StepArtifact, build_geometry_package` at module
   level. With `fdm_analysis` unimportable, importing
   `mcp_main.win.mcp.server` fails, so the whole MCP surface is lost
   (`session.py`, `transactions.py`, `actions.py` still import on their own).
   Blocking it is therefore a code change, not a packaging choice.

   Shipping a *subset* of files is also not possible as-is: `fdm_analysis/__init__.py`
   re-exports and `import fdm_analysis` transitively loads 17 submodules
   (conversion, delivery, geometry_pipeline, metrics, pipeline,
   slicers/bambu_studio, slicers/execution, …), so dropping the slicer and
   delivery modules breaks the package import before any consumer call runs.
   `fdm_analysis/` measures 224K — the format/decision is about dependency
   direction, not size.

   Three options for the human:
   - **A** ship the 224K package as a shared geometry-contract library
     (smallest change; widens the consumer surface to FDM code).
   - **B** split: move the contracts `geometry.py` needs (`StepArtifact`,
     `build_geometry_package`) into a neutral shared spot, or make
     `fdm_analysis/__init__` and the FDM-only submodules lazy, keeping
     slicers/Bambu/delivery/metrics/reports/conversion out of the artifact
     (requires code work in the development plane).
   - **C** exclude and accept a non-importable server — rejected as stated
     above.

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
