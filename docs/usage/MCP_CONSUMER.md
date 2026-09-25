# Onshape FeatureScript MCP usage

Audience: Production / User operating as an MCP consumer or calling agent

This document describes the public calling contract. It does not describe source
layout, development tests, Windows deployment, or repository maintenance. A
runtime MCP client must deliver the server's trusted, revisioned production-role
policy before the first tool decision, then prefer the exact tool schema; this
authored page is the stable usage source behind that surface. If tools are
visible but the `Production / User` and `Production / Operator` policy is not,
stop and route the client installation problem to an Operator.

## What the server provides

The server exposes four capability families:

- offline project, FeatureScript, and Onshape REST reference lookup;
- local project state, parameters, request construction, and quota inspection;
- guarded Onshape REST reads, evaluation, validation, rendering, and writes;
- Windows-hosted browser observation and browser workflows that consume zero REST quota.

The exact current surface is the MCP `tools/list` response. A derived repository
summary is available at `../generated/TOOL_REFERENCE.md`; it is not a substitute
for the runtime schema.

## Required lookup order

1. Classify the need as project documentation, FeatureScript, REST API reference,
   browser behavior, or a live operation.
2. Use the cheapest offline candidate index first.
3. Open one exact section, symbol, endpoint, schema, or tool definition.
4. Use complete authored/raw sources only when exact indexed detail is insufficient.
5. Prefer zero-cost local tools over browser or live REST operations.

Do not guess FeatureScript names, REST payloads, Onshape IDs, selectors, or tool
arguments that can be looked up through the server.

### Delegation and lookup depth (measured)

The required order sets the direction; this sets the depth a delegated agent may
spend. It is advisory routing economics and grants no authority.

- **Name the exact entry.** Handing a delegate one authoritative page was the
  cheapest depth on average (26.8k weighted units); making it decide *which*
  source is current was the dearest (37.0k). A delegate buys that decision with
  rounds.
- **Cost tracks rounds, not volume.** Across the 12 measured cells below,
  `corr(requests, weighted cost) = 0.92`, and the cheapest and dearest cells used
  6 and 18 requests. Cache reads are priced 0.025 against 1.0 for output, so a
  large cached read is not what makes a delegate expensive. A delegate that
  locates a section with `grep` and bounded reads stays cheap even when the
  material is one large file; one that must decide which of several sources is
  authoritative does not.
- **Prefer one delegate over a team for ordinary work.** One spawned delegate
  averaged 26.5k against 38.2k for an `agent_teams` member, and the whole
  difference was first-turn uncached input (team/task bootstrap), not discovery.
  Teams were also the most predictable route (1.32x spread against 2.05x/2.69x),
  so choose them for a bounded worst case, not for average cost. A workflow
  `agent()` stage behaved like a spawned delegate on average (30.3k) with the
  widest spread.
- **Forked delegation is not a work route.** A forked child is a memory
  continuation and was excluded from these figures.

| Lookup depth handed to the delegate | spawned delegate | `agent_teams` member | workflow `agent()` |
|---|---|---|---|
| specification inline in the prompt | 17.1k | 32.3k | 37.1k |
| one named authoritative page | 28.1k | 35.9k | 16.2k |
| a catalogue of notes, current one to be found | 25.5k | 41.9k | 43.6k |
| one ~195 kB concatenated dump | 35.1k | 42.7k | 24.1k |
| **mean** | **26.5k** | **38.2k** | **30.3k** |

Method: 3 delegation routes x 4 lookup depths, one fixed machine-checked task,
serial execution, gateway-reported usage in child session logs, and the report-02
weighting (output 1 / uncached input 0.25 / cache read 0.025). Per-cell figures,
tool traces and replay commands:
`onshape_docs/verification/delegation-lookup-cost-2026-09-21.md`. Limits: one
model route, one task, n=1 per cell, non-monotonic per-cell ordering, and all 12
cells passed on the first attempt — so this ranks cost only and says nothing
about which route succeeds more often.

## Capability routes

| Need | First public capability | Exact next detail |
|---|---|---|
| Project workflow or verified lesson | `docs_search` or `docs_list` | `docs_section` |
| FeatureScript orientation or symbol | `fs_quick_reference` or `fs_search` | `fs_get_function`, `fs_get_type`, `fs_guide_section`, then source if necessary |
| REST endpoint/schema/auth/error | `onshape_api_list_tags` or `onshape_api_search` | Exact endpoint, schema, auth, or error tool |
| Browser behavior/known workflow | Project docs search over browser experience | One exact experience section before browser action |
| Current tool arguments | MCP `tools/list`/tool schema | One selected tool schema |
| Quota/state before a live REST action | Local state and quota tools | Guarded operation only if still required |

## Cost and side-effect classes

### Offline/zero-Onshape-REST

Reference lookup, project-doc lookup, local state inspection, parameter loading,
payload construction, dry-run, mocks, fixtures, and quota-ledger inspection do
not contact Onshape. An explicitly requested reference-update tool may fetch
public zero-quota sources; read its exact schema and description before calling.

### Concurrency and workflow isolation

One backend, one browser/profile owner, and serialized `tools/call` requests do
not make a sequence of calls atomic. The current production contract supports
multiple clients only for reads whose catalog
`concurrency.safeDuringMutationWorkflow` is `true`, or whose
`safeDuringMutationWorkflowWhenExplicitTarget` is `true` with every applicable
`scopeKeyPaths` argument supplied. The contract is schema-derived and
`conditionEvaluatedAtRuntime=false`; the caller must verify actual argument
presence, and a configured default target is never allowed for concurrent use.
Explicit-target reads may still observe a document mid-mutation and must not be
used as final acceptance evidence. This read allowance exists alongside one
modifying agent at a time. Multiple modifying agents are unsupported until
scoped document leases have end-to-end acceptance evidence.

The modifying agent owns one exclusive workflow from its first target selection
through navigation, mutation, shared-state synchronization, final acceptance,
and browser release. Do not split operations that depend on the current page,
current Part Studio, or cached REST target across agents. REST operations used
concurrently must carry explicit target IDs; a tool marked
`requiresExplicitTargetForConcurrentUse=true` cannot use its configured default.
On `client_lease_busy`, wait or exit without starting another MCP or browser.

`mcp_tool_catalog` exposes a conservative `cost.concurrency` contract for every
tool. `access` is `shared_read`, `connection_local`, or `exclusive_workflow`;
`scope` is the governing scope, while `coordinationScopes` records additional
browser-profile plus document/target coordination needed by future leases.
`scopeKeyPaths` lists schema-visible opaque target arguments but does not prove
they were supplied. `sharedTargetState` and `sharedLocalState` identify state
that another exclusive tool may update; those readers are not safe during that
mutation. `workflowIsolation="none"` is deliberate: this metadata supports
scheduling and future scoped leases but does not itself acquire a lock or grant
mutation authority. `registered=true` and request serialization are not health
evidence for document-level mutation isolation.

### Browser operations

Browser tools consume zero REST API quota because they drive the Windows browser.
`browser_session(action="release")` closes only the browser/context owned by the
current MCP process, releases that process's persistent-profile ownership, and is
idempotent when no browser was started. **Keep the browser session at the end of a
task by default.** Release only on an explicit human request, or when resources
genuinely must be freed: release CLOSES the window and can drop the persistent
profile's login state, so a later task may pay another human sign-in. It cannot
close a browser owned by another MCP process; profile contention across processes
is an Operator/lifecycle failure, not authority to delete lock files or kill
another owner. Three outcomes are not interchangeable: `release` can lose login
state; a process crash or a page navigation does not; and
`browser_session(action="detach")` keeps the window but is supported only in
resident/attached mode (`browser.resident = true`) — a non-resident session
returns `detached=false`, `supported=false`, and recommends release. This is a
**structural** limitation, not a missing wheel API (shared-library maintainers,
2026-09-25): a `launch_persistent_context` browser runs on
`--remote-debugging-pipe`, so it exposes no CDP endpoint to re-attach to, and the
Playwright driver owns its whole process tree (on exit it reaps it with
`taskkill /T /F`). Do not ask for a keep-alive detach on that launch mode and do
not retry it; **when login state must outlive the MCP child, use resident mode
instead** — `browser.resident = true` has the server spawn Edge detached with
`--remote-debugging-port` and attach over CDP, where `context.close()` is already a
detach (measured on `Edg/153.0.4234.32`). `browser_session(action="login")` reports `alreadyAuthenticated` (the
persistent profile still has a live session) or `needsHumanLogin` (it does not),
so the caller no longer has to guess from the URL. When it does need a human, the
result also carries `pageMaySelfReload: true` and a `humanInputAdvisory`: the
Onshape sign-in page reloads **itself** while the human types (measured — it
replaces its own document, so typed input and all window-level state are lost),
and this server neither causes that nor can prevent or recover it. **Do not poll
or read the sign-in page during human input**; wait for the human to report
completion and then decide with `action=health` rather than page reads.
`browser_session action=status`
also reports `pageSelection` (`{"considered", "discarded":[{"url","reason"}],
"selected"}`) from the last `start()`, and the session never adopts a closed
candidate page: it skips closed pages, advances past an adopt failure, and falls
back to opening a new page.

| Session ending | Closes the window? | Drops the profile's login? | When to use |
|---|---|---|---|
| `browser_session action=release` | Yes | Maybe — it reports `loginStateMayNeedRefresh` and is the only one of the three that can | Only on an explicit human request, or when resources genuinely must be freed |
| `browser_session action=detach` (resident/attached mode only) | No (`contextClosed: false`, `browserLeftRunning: true`) | No | Hand back MCP ownership while leaving the browser, its tabs and its login alone |
| Process-level crash / termination | The owned browser goes with the process | No — the persistent profile keeps its login and reopening reuses it | Unexpected; no cleanup action is needed to preserve the login |
| Page navigation / reload | No | No | Ordinary page recovery; never treat it as a session ending |

The launched browser is a real Edge channel (`channel = "msedge"`) using a
persistent, checkout-local profile (`user_data_dir`, default
`user_data/onshape_profile`). It does not reuse the OS Edge primary profile, but
on a machine whose Windows account is a Microsoft account Edge signs a fresh
profile in automatically, so the window is not anonymous even though Edge created
the profile directory; screenshots and every page the agent reads are
attributable to that account. That automatic sign-in is **Edge's own documented
default**, not this server's doing: it is Edge's *implicit sign-in*, enabled by
default on Windows, which signs the browser profile in from the OS sign-in — so
choosing another profile directory does **not** change the identity. It only
affects the Edge profile identity; it does not copy the primary profile's cookies,
which is why the Onshape session still starts empty here. Suppressing it requires
a **machine-wide** Edge policy (`ImplicitSignInEnabled=0`, or `BrowserSignin=0`
with `NonRemovableProfileEnabled=0`, under `SOFTWARE\Policies\Microsoft\Edge`);
this repository never writes those, because they would also change the Edge the
human uses normally. `browser_session(action="status")` reports
`profileDir`, `profileBytes`, `profileBytesComplete` (the walk is file-capped, so
`complete=false` is a lower bound), and `accountMarkerDetected` (a boolean from
recursive name matches of known Edge account keys; it is Edge-version dependent,
and `false` means "no marker found", NOT "anonymous" — no account value is ever
returned). A separate profile directory can be selected with the optional
`isolated_user_data_dir` key in `onshape_browser_mode/config/browser.toml`; that
is only a directory choice, and the trade-off is explicit: Onshape login
persistence is bought with a persistent profile, so a separate directory means a
fresh or explicitly isolated identity. Guest mode (`--guest`) is deliberately NOT
implemented. To clear the profile, sign out of the Edge account in that window
(that does not clear cookies, so the Onshape login survives); deleting the
directory is the most thorough and costs one manual sign-in.

`browser_export_step` gained `overwrite` and no longer reports a false failure
when the STEP was already saved. A failure returns a **structured** result
instead of raising: `exported: false`, `failure: {phase, error}` (phase is one of
`stage_artifact`|`save_download`|`close_internal_download_pages`|
`wait_for_dialog_hidden`|`register_manifest`), `stagedArtifacts`
(`[{path, fileName, bytes, sha256}]`), `stagingComplete`, `alreadyStaged`,
`browserAliveBefore`, `browserAliveAfter`, and `recovery` (a LIST of candidate
next actions), plus the existing zero-cost annotations. A failure at phase
`wait_for_dialog_hidden` with `stagingComplete: true` is NOT a download failure:
the STEP is on disk with its manifest and is reusable (for example by
`browser_build_geometry_package`), and a same-`export_id` retry then returns
`alreadyStaged` success instead of the old "staging destination already exists"
refusal. Pass `overwrite=true` on a retry to reuse a staging directory a failed
export left partial; without it a retry refuses rather than overwrite leftovers.
Reuse is granted on **provenance**, not merely on the artifact being intact: the
manifest records the document/workspace/element it was exported from, and a call
naming a different target is refused ("holds a STEP exported from a different
document/workspace/element") rather than answered with the other document's STEP.
`overwrite=true` replaces such a staging directory instead. The `dry_run` plan
reports `stagingProvenanceChecked`/`stagingProvenanceMatches` so it never
advertises a reuse the real call would refuse; with no target ids it reports the
artifact-level answer and `stagingProvenanceChecked: false`.
Pre-flight validation failures (bad tab, URL mismatch, non-STEP download) still
raise. A complete staging requires manifest + artifact + matching sha256. A
failure may restart the browser or leave the MCP child holding no browser
resources. `browser_session action=health` separates those two: `pages: []` still
means only "this MCP process holds nothing", but in resident mode
(`browser.resident = true`) the probe additionally reads the detached browser's
own loopback DevTools endpoint and reports it as `residentBrowser`. So
`browser_not_running` now means no browser answered at all, while `ok` with
`residentBrowser.observed: true` means the detached browser is alive and still
holding an Onshape page: its login survived this child, and any browser call
attaches to it without a human sign-in. That read launches nothing, attaches
nothing, evaluates no page, and navigates nowhere. `status` reports the same
`residentBrowser` observation, so a browser that is merely unheld is never
described as dead.

Read-only observation should come first. `browser_fs_read_notices` opens and
restores the active FeatureScript notice pane and returns normalized notice rows;
`browser_get_fs_compile_status` combines those rows with Ace annotations, while
`browser_get_fs_symbols` reads the Module-outline inventory. `browser_fs_read_notices`
demotes stale (`outOfDate`) notices by default: `notices` carries current rows,
`staleNotices` carries the raw out-of-date rows, and the result also carries
`staleNoticeCount`, `staleErrorCount`, `staleErrorCountBasis`,
`currentNoticeCount`, `returnedNoticeCount`, `includeStale`, and per-notice
`stale` + `bucket` (`stale`/`currentActiveTab`/`currentOtherElement`). Pass
`includeStale=true` to also return the raw stale rows inside `notices`. A stale
notice's line number points at a different source version, so never read it as
current state. FeatureScript deployment succeeds only when the Commit state
transition, exact source readback,
and combined compiler evidence verify with no blocking warning/error. Every
committed deployment attempt also writes a local diagnostic package containing
the full source and compile result under
`onshape_browser_mode/outputs/fs_diagnostics/`; the experimental, default-hidden
`browser_fs_capture_diagnostic` creates the same package on demand. These local
artifacts can contain proprietary source code and must be protected accordingly.
`browser_get_partstudio_features` rows carry `errorText` (read from the row's
`data-bs-original-title` for errored rows in the same pass), and the result
carries `hasErrorReadAt` plus `maybeStale`, so read `hasError` together with when
it was read. `browser_deploy_featurescript` activates the Feature Studio tab
itself when the active tab is a Part Studio, and otherwise returns an explicit
instruction to call `browser_activate_tab` first. `browser_verify_feature_parameters` backs parameter verification with
a bounded convergence reader: a read taken while the row is still regenerating is
NOT reported as a failure — it returns `parametersApplied: null` with
`retryVerify: true`, `maybeStale: true`, `hasErrorReadAt`, and `settleCondition`
(one of `cleanFirstRead`|`clearedOnReRead`|`stableError`|`unstableTimeout`, plus
`settleAttempts`, `settleWaitedMs`, and `settleTimeoutMs`). The part summary keeps
`partItems` as a list of strings and adds `partCounts` (counts by name, first-seen
order), `duplicateNames` (`[{name,count}]`), `duplicateNameCount`, and
`partNameDetails` (`[{name,count,possibleDuplicateName[,note]}]`). The duplicate
marker is a NAME-based observation only and makes no geometry claim: per-part
volume, a sliver-area threshold, and a connectivity report are not implemented
and cannot be derived without a geometry or REST path.
The 22 transactions promoted from the planned registry
are in the complete browser registry; ordinary `tools/list` uses the default
`gateway` exposure (see Dynamic tool display). FS insertion writes require dry-run
and confirmation; fold/navigation and app-shell observations are zero-REST UI
operations. Drawing auto-view success requires exactly one new tab plus DOM or
decoded-canvas view evidence. The draft-analysis-based
`browser_print_orientation_check` and its dependent `browser_print_optimize_part`
were semantically invalid — draft analysis is not an FDM orientation engine — and
were removed from the surface on 2026-09-19 rather than left as fail-closed
names; do not call them and do not expect a browser print-analysis tool until a
slicer-backed module is designed. A real click, type, submit, create, delete,
deploy, assemble, or drawing
action can still mutate the cloud document and requires the tool's confirmation
contract. Also inspect catalog `sideEffects`: screenshot/report artifacts,
recorder state, persistent login profiles, and local caches can be written even
when the Onshape operation itself is cloud-read-only. Prefer exact-ID
`browser_delete_element` over the deprecated name wrapper, and one drawing
transaction: `browser_draw_part_with_views` with `part_name` for verified views,
with `dimensions` to dimension the current Drawing frame, or with both.

#### Six-level browser selection

Semantic level is optional discovery metadata, not registration, permission, or
execution policy:

- L1: generic browser primitive.
- L2: composite generic browser transaction.
- L3: Onshape-aware prepare/inspect/recovery interaction without domain success.
- L4: one completed and verified Onshape transaction or complete observation.
- L5: multi-transaction Onshape workflow.
- L6: independently consumable deliverable with final acceptance and manifest.

Project control is outside L1-L6 and coordinates one or more L6 nodes. Ordinary
selection ranks L5 workflows first, then L4 verified transactions/observations,
then L2 generic browser transactions, then L6 deliverable recipes. This maximizes
reuse of completed workflows while reserving L6 for an explicitly requested
independent artifact/manifest boundary; do not decompose a suitable candidate into
lower levels automatically. L1/L3 are omitted from
ordinary discovery to save context, but their existence and purpose are not
secret: call `browser_discover_tools` with `semantic_levels=["L1"]` or
`semantic_levels=["L3"]`, inspect the returned exact schema, then call that
candidate by its exact registered name; `mcp_tool_catalog` returns the same exact
name and full schema. There is no separate invocation entry point to route
through, and no discovery step bypasses confirmation or handler acceptance. An
`Internal-only`
tool is hidden the same way: `browser_fix_instances` and
`browser_group_instances` act on a selection context that only
`browser_assemble` establishes, so they are callable by exact name and visible
through `browser_discover_tools` at their explicit level, but absent from the
ordinary list. Unclassified tools remain valid and visible by default. Set
`ONSHAPE_MCP_TOOL_EXPOSURE=static` only for complete-registry compatibility or
debugging.

##### Compressed entry points (`gateway`, the default)

`gateway` is the default tool exposure when nothing else selects a mode. It
advertises a small declarative surface:

1. A discovery core — `mcp_tool_catalog`, `mcp_tool_view`, and `mcp_tool_invoke`.
   The invoker is the advertised door to the names this view does not list: it
   forwards one call to any registered tool by exact name and the target's own
   gates still answer. It is listed in every exposure mode, because a client that
   refuses unadvertised names (measured live 2026-09-21) cannot use a hidden one.
   The set is sized by measurement, not by a token target — see
   `docs/roadmap/LOOKUP_DEPTH_RESEARCH.md`.
2. Curated representatives covering every category, each of them a step the
   recorded sessions actually drove: `browser_session`, `browser_get_page_tabs`,
   `browser_create_tab`, `browser_activate_tab`, `browser_get_partstudio_features`,
   `browser_insert_custom_feature`, `browser_delete_feature`, the parameter
   workflow (`browser_edit_feature_parameters`, `browser_verify_feature_parameters`,
   `browser_read_feature_parameters`), `browser_deploy_featurescript`,
   `browser_run_project`, `browser_discover_tools`, `browser_export_step`, and
   **both steps** of each prescribed reference chain (`docs_search` +
   `docs_section`, `fs_search` + `fs_get_function`, `onshape_api_search` +
   `onshape_api_endpoint`), plus `onshape_api_quota` and `onshape_geometry_status`.
   A chain is listed end to end on purpose: listing its first step alone made the
   documented workflow pay a hidden-name round every time.

The curated names exist so ordinary work does not have to start with a lookup:
retrieval is not free (a three-result `search` is ~6.8 kB, one modelling
`describe` ~10.5 kB), which is why the surface is not search-only. When a lookup
IS needed, prefer the cheap path:

1. `mcp_tool_catalog` with `action=index` — one line per category (~1.3 kB). Add
   `category=<browser|rest|rest_reference|featurescript|documentation|control>` to
   get that category's tools as bounded `name -- purpose` lines, paging with
   `offset` when the answer says `truncated`.
2. `action=describe` with the exact name only when you need the full schema.
3. Call any registered name as a normal `tools/call`, advertised or not — or, if
   the client refuses names absent from `tools/list`, call `mcp_tool_invoke` with
   that exact name and its arguments. Both routes reach the same handler, so the
   handler's own `confirm_mutation`, dry-run, cost, and acceptance gates are what
   answer; the gateway changes only what is advertised.

`gateway` is the built-in fallback: with no explicit argument, no
`ONSHAPE_MCP_TOOL_EXPOSURE`, and no `tool_views.local.toml`, a connection starts
in `gateway`. Precedence is an explicit argument, then
`ONSHAPE_MCP_TOOL_EXPOSURE`, then
`mcp_main/win/mcp/config/tool_views.local.toml [exposure].mode`, then `gateway`.
Change it on a host whose launcher owns the child environment by copying
`tool_views.local.toml.example` to `tool_views.local.toml` and setting `mode`;
the environment variable still wins over the file, and the MCP process must
restart to apply it.

Measured (2026-09-21, `dev/tools/context_cost.py`, recorded in
`onshape_docs/verification/context-cost-surfaces-2026-09-21.json`): the registry
of 111 tools renders as 227,459 chars in `static`, 167,441 chars for 77 tools in
`semantic`, 89,527 chars for 40 tools in `profile=browser`, and 66,051 chars for
25 tools in `gateway` (3.4x smaller than the registry, 2.5x smaller than
`semantic`). `dynamic` adds a collapsed cold start of 3 tools
(`mcp_tool_catalog`, `mcp_tool_view`, `mcp_tool_invoke`) and, once expanded,
shows `static`/`semantic`/`gateway`/`profile` as 111/77/25/40 tools. These are
advertised **tool-table sizes** (characters, with a documented token estimate),
not end-to-end task cost; they are not a mode ranking for complex tasks and must
not be extrapolated into one (see
`onshape_docs/verification/delegation-lookup-cost-2026-09-21.md`). A client that
refuses unadvertised names does not need a different mode: `mcp_tool_invoke` is
advertised in every mode and forwards one call to any registered tool by exact
name, with the target's own confirmation, cost and dry-run gates intact.

Mutation answers are compacted on the same principle: a row list that would repeat
the same Feature List several times is reported as a count, and
`include_row_evidence=true` restores the full evidence on
`browser_insert_custom_feature` and `browser_delete_feature`.

#### Tool catalog search and description

`mcp_tool_catalog` is the lookup-first entry for MCP capabilities across all
modules and profiles. Its immutable index is built once from the complete
registered `TOOLS` surface after cost metadata and browser tools are installed;
it does not maintain a second hand-authored catalog.

Use the bounded sequence:

1. `action=status` to read the registry fingerprint, counts, filters, and result limits.
2. `action=search` with a short query and, where known, `modules`, `profiles`,
   `semantic_levels`, `network`, `mutating`, or `visible_only`. Search defaults to
   8 results and cannot exceed 12. It returns compact summaries and never returns
   `inputSchema`.
3. `action=describe` with one exact result name to load the full current
   `inputSchema`, cost, annotations, profiles, browser semantics, view visibility,
   confirmation mode, explicit local/session `sideEffects`, and conservative
   concurrency contract. `action=status` reports that workflow isolation is
   currently `none` and production mutation mode is `single_modifying_agent`.
4. Treat `confirmation.mode=always` as unconditional, `non_dry_run` as required
   only for real execution, and `budget_override` as a session-budget override
   rather than mutation approval. `confirmation.schemaRequired` reports the JSON
   Schema contract separately.
5. Call the described tool normally. Catalog output does not grant confirmation,
   quota, browser, credential, or mutation authority.

Search always covers the complete registry, including tools absent from the
current `tools/list`; `visibleInCurrentView` is informational. Exact-name and name
prefix matches rank before description matches. Profile names are structured
filters rather than free-text tokens, preventing ubiquitous control tools from
polluting capability searches. Cache search/describe results against the returned
SHA-256 `fingerprint`; refresh the cache when it changes.

Three result-shape rules matter when routing a modeling request:

- A query that names a CAD feature also returns `capabilities`: bounded
  whole-feature capability cards, each with an `invocation` naming
  `browser_deploy_and_apply_featurescript` plus the `capability` and the card's own
  default `values`. A capability is **not** a registered tool, so it never appears
  in `results`, and it is invoked as the deploy tool's `capability` argument,
  not by name.
- A non-empty query the tokenizer cannot read (Chinese, for example) matches no
  tool summary. It used to match the whole registry, which looked like a broad
  search and was a routing failure; such a query can still resolve a card.
- An empty query still browses the registry in ranking order.

#### Dynamic tool display (collapse/expand)

Tool display is a connection-scoped context and routing convention, never an
authorization boundary. The complete `TOOLS`/`HANDLERS` registry remains loaded;
a known-name `tools/call` and internal composition remain available when a tool
is absent from the current `tools/list`, and the eight absorbed compatibility
names still answer by exact name. Confirmation, quota, browser pacing, cost, and
acceptance gates remain authoritative.

`dynamic` is the collapse/expand **control**, orthogonal to which display set is
shown once expanded. A fresh `dynamic` connection starts **collapsed** and lists
only the three control/discovery entry points — `mcp_tool_catalog`,
`mcp_tool_view`, and `mcp_tool_invoke` — with no domain-tool schema resident.
`mcp_tool_view` drives it:

- `action=status` returns `state` (`"collapsed"`/`"expanded"`), `expandedView`,
  and `scope` (`"connection"`), alongside its prior keys.
- `action=expand` opens a display set; `expanded_view` selects
  `static|semantic|gateway|profile` and defaults to the current set, which on a
  cold start is `gateway`.
- `action=collapse` returns to the three entry points; it is explicit, never an
  implicit side effect.
- `action=set` is the compatibility alias for `expand`, defaulting to the
  connection's startup-profile view.
- `action=reset` returns to a cold start: collapsed, `gateway`, and the
  connection's original startup profile.

**Scope, stated plainly: view state is CONNECTION-scoped, not
conversation-scoped.** A stdio server sees a connection and the messages on it,
not the separate conversations a client may multiplex over that one connection.
If a client reuses or shares a connection, an `expand` performed for one
conversation is observed by every conversation on it. Do not claim
per-conversation isolation.

**Collapse is pure in-memory state.** It writes nothing locally or remotely, it is
not exiting the browser, and it is not a permission change. Hidden and unknown
names remain callable by their exact registered name, and every confirmation,
quota, pacing, and permission gate still answers. Every *effective* change emits
`notifications/tools/list_changed`; a repeated call that changes nothing emits
nothing.

The other fixed modes are explicit:

- `static` keeps the complete registry visible.
- `semantic` selects the bounded ordinary view as a fixed display set.
- `profile` selects one fixed `ONSHAPE_MCP_TOOL_PROFILE` at connection start.
- `gateway` is the built-in default view (see above).

Profiles are `default`, `browser`, `rest`, `featurescript`, `documentation`,
`geometry`, and `all`. An optional `semantic_levels` list narrows classified
browser tools. `mcp_tool_view`, `mcp_tool_catalog`, `mcp_tool_invoke`,
`browser_session`, and `browser_discover_tools` remain available as
navigation/recovery surfaces in the relevant view; the absorbed compatibility names
do not, and are reachable only by exact name, through `mcp_tool_invoke`, or through
`mcp_tool_view profile=all`.

Correct dynamic-client flow:

1. Configure `ONSHAPE_MCP_TOOL_EXPOSURE=dynamic` and an optional startup
   `ONSHAPE_MCP_TOOL_PROFILE`, then restart the MCP process/client adapter.
2. Check initialize capability `tools.listChanged`. If false, use a fixed view or
   the gateway; do not assume the client can refresh dynamically.
3. Call `mcp_tool_view` with `action=status` before changing the view.
4. Call `action=expand` with an optional `expanded_view`, `profile`, and browser
   semantic levels (`action=set` is the legacy alias), or `action=collapse` to
   return to the control-only list.
5. After `notifications/tools/list_changed`, issue a fresh `tools/list`; replace
   the client's displayed tool schemas instead of appending to a stale list.
6. Use `action=reset` to return to a cold start (collapsed, `gateway`, startup
   profile). Reconnecting also creates a fresh view and does not inherit another
   connection's state.

A repeated change that does not alter the effective view emits no notification.
Clients that ignore `list_changed` should reconnect, refresh manually, or stay in
a fixed mode. Never interpret a missing displayed tool as denied or a displayed
tool as authorized.

### Live REST reads/evaluation/rendering

These consume annual API quota even when they do not mutate the model. Use them
only for a specific fact that cannot be obtained offline. Provide explicit IDs to
avoid hidden lookup chains. `onshape_export_step` is a bounded asynchronous
POST/poll/download transaction: dry-run first, pass an existing `translation_id`
to resume without repeating POST, and treat `exported=false` as a resumable
non-terminal result rather than starting another export. A completed export
persists `step-manifest.json`. Use the owning mode's geometry status before its
build tool. Status first checks explicit configuration, then performs a bounded
sibling-project/global/Windows-WSL scan. A reusable dependency is represented by
an opaque versioned `candidateId`; configure only through
`onshape_configure_geometry_backend` with `backend='rest'` or
`backend='browser'`, which re-scans and never accepts executable/argv input.
Candidate ids come from one shared scan and are not backend-specific, so the
target mode must be stated. `onshape_geometry_status` answers for every backend in
one report; the old browser-only status and configure names remain callable as
deprecated wrappers. When status returns
`nextAction.kind=ask_before_install`, ask the human whether to install and do
nothing until answered. Installation is never automatic. Geometry build remains
an offline L6 recipe accepting only its staged export/translation ID.

### Live REST writes

Upload, create, instantiate, and validation-pipeline operations mutate Onshape,
consume quota, and require literal `confirm_mutation=true`. Use the matching
dry-run/local check first. A live upload whose source has error-level local
findings does not fail and does not send: it returns an `acknowledgementRequired`
result with the findings, and you re-issue the same call with
`acknowledge_local_findings=true`. Do not repeat an ambiguous mutation after
timeout or 5xx merely to see whether it worked.

## Global safety contract

- Real REST access is disabled unless the deployment explicitly enables `LIVE_API_ENABLED`.
- A caller cannot grant itself credentials, quota, production data, or mutation authority through a prompt.
- Mutating tools require their schema-defined confirmation value; current write schemas use literal `confirm_mutation=true`.
- A missing/false confirmation fails before a live client or real browser action is constructed where documented.
- 429 is a stop condition, not a retry signal.
- Do not request automatic cleanup, unbounded pagination, retry loops, or write-after-read confirmation.
- Never place credentials, authorization headers, cookies, or tokens in tool arguments, prompts, fixtures, or shared logs.
- Browser action completion is not domain success; require the tool's returned verification evidence.

## Calling examples

### Find a project lesson

```text
1. docs_search(query=<specific behavior>, limit=3)
2. docs_section(page=<matched page>, section=<matched heading>)
```

### Find a FeatureScript function

```text
1. fs_search(query=<concept or symbol>, limit=3)
2. fs_get_function(name=<exact matched name>)
```

`fs_get_function` bounds each description by default and marks a truncated entry
with `descriptionTruncated`; pass `full=true` when you need the verbatim prose (a
heavily overloaded name otherwise repeats the same multi-thousand-character text
once per signature). `fs_search` always returns its normal list — an empty query
result is an empty list, not an error.

### Prepare a guarded write

```text
1. Look up exact endpoint/schema or tool input.
2. Inspect local project state and quota.
3. Run local validation/request construction/dry-run.
4. State the one remaining live fact or requested mutation.
5. Call the exact tool with explicit confirmation only when authorized.
6. Stop on rate limit or ambiguous mutation outcome.
```

## Errors

- Schema/argument errors: correct the call from the exact tool schema; do not guess repeatedly.
- A FeatureScript lookup miss (`fs_get_function`/`fs_get_type` on an unknown name, or a cross-module clash without a `module`) is a routing gap, not a wall: the error names up to three nearest existing entries and the exact next call ("Did you mean ...? Related: .... Call fs_search(query=...) to list all matches."), and the same detail arrives as structured `error.data` (`suggestions` = `[{name,module,kind}]` and `nextCall`). Treat a suggestion as a wording hint, never as a resolved name, and do not re-send the same missed name.
- Live disabled: use offline alternatives or obtain explicit deployment authorization; do not try to bypass the gate.
- Quota shortfall/rate limit: stop and preserve the returned budget/retry evidence.
- Missing credentials/session: route to the Operator; a User prompt cannot create those authorities.
- Browser verification failure: inspect the returned evidence and use documented read-only discovery before another mutation.
- Version/reference conflict: report the observed and vendored versions and use the version tools; do not merge stale facts silently.

## Compatibility and authority

The runtime tool schema and current server behavior are authoritative for calls.
The canonical runtime policy routes product capability use to User and runtime
installation/availability/recovery to Operator; role transitions are explicit
and do not merge permissions. A supported client consumes native initialization
instructions or an installation-generated companion from the same server
revision. A tools-only connection is unsupported. The generated tool reference
is a derived snapshot. Public behavior changes must update schemas, tests, this
usage contract where relevant, and the generated reference together.
