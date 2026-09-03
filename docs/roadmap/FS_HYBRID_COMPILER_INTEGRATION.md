# FeatureScript hybrid compiler integration roadmap

Status: proposed development direction; no compiler implementation is claimed by this document.

## Purpose and authority

This roadmap integrates `Onshape_MCP_FS_Hybrid_Compiler_Agent_Execution_Spec_v2.md`
with the repository's current verified architecture. It turns the source proposal
into a development sequence that preserves the working MCP while establishing an
FS-first hybrid compiler line.

This page owns the integration plan. It does not override:

- current behavior defined by code, tests, registered schemas, and handlers;
- current module ownership in `docs/architecture/OVERVIEW.md` and `docs/modules/`;
- REST quota, confirmation, retry, credential, and live-request constraints;
- browser profile ownership, pacing, mutation, and acceptance constraints;
- the distinction between roadmap proposals and implemented capabilities.

Evidence labels used below:

- `verified`: implemented behavior supported by current code/tests/contracts;
- `inferred`: a risk or boundary derived from current behavior;
- `proposal`: future compiler behavior that is not implemented yet.

## Architectural decision

The target is not a larger public browser-tool inventory. The target is:

```text
Agent FS source or patch
  -> local frontend and semantic analysis
  -> Feature IR + model bindings
  -> partition and lowering plan
       -> Native Transaction IR -> versioned browser driver
       -> whole-feature or later Custom island -> FS deployment backend
  -> apply with explicit mutation authority
  -> inspect and verify
  -> export when requested
```

Development should occur on a compiler fork or equivalent new implementation
line that retains the current Git history. The stable line remains usable as the
fallback and reference implementation. Reuse should happen through explicit
module ports and adapters, not by copying the existing REST/browser code into a
second implementation.

Existing implementation details may be reorganized in the compiler line, but
existing safety and ownership invariants remain architectural constraints until
an explicit, reviewed contract replaces them.

## Current baseline

### Verified reusable assets

| Target subsystem | Current owner/evidence | Reuse decision |
|---|---|---|
| A. REST operations and oracle inputs | `onshape_rest_api_mode`, REST reference index | Reuse request construction, live gate, quota guard, state, dry-run, replay, export, and selected inspection operations behind a port. |
| B. Browser control plane | browser session, document/tab operations, page state | Reuse through a browser-control adapter. Keep document/application control separate from modeling semantics. |
| C. Raw browser runtime | `onshape_browser_mode.interaction`, page/frame primitives, L1 handlers | Reuse as a default-hidden rescue and driver layer. |
| C2. Onshape-aware browser library | `transactions.py`, `semantic.py`, `modeling_transactions.py`, FeatureScript deploy/apply workflows | Reuse behind native-driver and Custom-backend interfaces. Do not make new compiler mappings public MCP tools. |
| Existing FS preflight | `onshape_docs/scripts/fs_local_check.py` | Preserve as one diagnostic pass; do not treat it as a parser, type checker, or lowering proof. |
| E. Observation inputs | screenshots, view orientation, Drawing canvas checks | Reuse capture mechanisms. A stable in-repository vision inference backend does not yet exist. |
| F. Export inputs | guarded REST STEP, browser STEP, geometry package/STL | Reuse backend implementations. A unified multi-format Export Manager remains proposed. |
| G. Inspection inputs | browser feature/part reads, REST checks, render/bounds, project assertions | Normalize through a new provenance-bearing model snapshot instead of exposing backend-specific results to compiler passes. |
| K. Knowledge plane | `onshape_docs`, vendored references, search/detail indexes, browser evidence and fixtures | Reuse as the lookup foundation; add compiler-owned mappings and fixtures without inventing another documentation system. |
| MCP exposure | complete registry, bounded catalog, fixed/profile/dynamic views, runtime prompt | Reuse as the public facade. Add only a small compiler surface and retain client compatibility tests. |
| Project orchestration | project schema v2 DAG, assertions, manifests, checkpoint/resume | Reuse above transaction execution; it is not itself Transaction IR or rollback machinery. |

Recent FS browser work is part of this baseline: deployment acceptance combines
Ace annotations with the FeatureScript notice pane, fails closed when blocking
notices cannot be read, and records a module-owned full-source diagnostic package.
That strengthens the Custom backend but does not make automatic fallback safe.

### Baseline corrections to the source specification

#### REST coverage is not a complete executable mirror

The repository has complete/broad offline REST reference lookup plus selected,
guarded REST operations. It does not currently register an executable wrapper
for every indexed public endpoint. Phase 0 must produce an endpoint-to-handler
coverage matrix before planning Inspector or oracle work. Missing execution
coverage is new work, not a completed asset.

The compiler must never turn documentation lookup into an implicit live request.
Every live oracle observation still requires one unresolved fact, an explicit
request budget, fixture destination, and stop condition.

#### The existing local checker is structural

`fs_local_check.py` catches high-value structural failures and warns about symbols
missing from the vendored index. It does not provide the scope, type, unit, query,
control-flow, effect, or import analysis required for native lowering confidence.
It remains useful before and alongside the future frontend.

#### Custom deployment is destructive without compiler isolation

The current browser deployment workflow replaces the active Feature Studio editor
contents, commits the source, may create a version, and inserts a Custom Feature.
It cannot be called as an automatic fallback against an arbitrary/default Feature
Studio.

Before a compiler can use it, the Custom backend needs compiler-owned storage,
stable naming, content hashes, source preimage handling, version reuse/retention,
multiple-output handling, and idempotent re-execution rules.

#### Hidden tools remain callable by known name

Current semantic/profile views optimize context. They are not authorization gates.
Existing C/C2 tools may remain registered for stable-line compatibility, but new
native feature mappings should be internal backend functions. If a future tool
must be development-only, that requires a real capability/role contract rather
than tools/list hiding.

## Target ownership and dependency direction

Introduce a new compiler core, tentatively `onshape_fs_compiler`, on the compiler
line. The final package name is a Phase 0 decision, not an implemented module.

```text
mcp_main
  -> onshape_fs_compiler.application
       -> frontend adapters
       -> semantic passes
       -> FeatureIR / SelectionIR / OpaqueRegion
       -> ModelBindingTable
       -> capability registry and partitioner
       -> CustomLowerer / NativeLowerer
       -> ExecutionPlan / TransactionIR state machine
            -> BrowserBackendPort -> onshape_browser_mode
            -> InspectorPort      -> browser and REST adapters
            -> KnowledgePort      -> onshape_docs
            -> ExportPort         -> browser and REST export adapters
```

Dependency rules:

1. The compiler core does not import MCP protocol code.
2. The compiler core does not own Playwright sessions, selectors, credentials,
   quota ledgers, or browser profiles.
3. `mcp_main` adapts a small public compiler contract and does not implement
   parsing, partitioning, lowering, selection, or recovery.
4. Browser selectors, coordinates, localized labels, waits, and raw events remain
   below Transaction IR.
5. REST access remains explicit through the REST owner; no compiler pass performs
   hidden discovery or validation requests.
6. Runtime compiler mapping data belongs to the compiler module. Test captures and
   replay fixtures remain under `dev/`; generated indexes remain generated.
7. Full FS source, screenshots, and cloud-derived fixtures are treated as
   potentially proprietary. Their owner, ignored/committed status, redaction, and
   retention must be explicit.

## Compiler contracts

### Compile unit and source of truth

Initial policy remains:

> Onshape is the authoritative live CAD state; FS is the Agent modeling/patch language.

The initial compiler does not promise bidirectional Part Studio-to-FS round trips.
A plan must identify an exact document/workspace/element and carry a base-state
token derived from an inspection snapshot. Apply rechecks that token before its
first mutation and fails closed if the target changed.

The first compile-unit contract should be a complete exported feature or complete
FeatureScript file. Arbitrary source-region islands are deferred until dependency
closure and ABI work exists.

Local source input must also have an explicit boundary. Prefer source text or a
compiler-owned workspace artifact ID. Do not allow an MCP tool to read arbitrary
host paths merely because the Agent refers to a local `.fs` file.

### Frontend and diagnostics

The community FeatureScript language-support implementation is a candidate, not a
selected dependency. A bounded technical spike must establish:

- repository and pinned commit/version;
- license, provenance, update, rollback, and supply-chain policy;
- supported FeatureScript language versions;
- grammar recovery and stable source spans;
- import/module, scope, overload, type, unit, query, and control-flow coverage;
- deterministic AST serialization and diagnostics;
- behavior for unknown or unsupported constructs.

If the frontend is implemented in another language, prefer a pinned subprocess
that emits a versioned JSON AST/diagnostic contract. Do not couple the Python MCP
runtime directly to an unstable language-server internal API.

Confidence is fail-closed:

```text
recognized and proven native subset -> native lowering may be planned
valid FS but unsupported lowering    -> Custom lowering may be planned
semantic uncertainty                 -> reject or request source repair
```

### Feature IR

Feature IR is versioned, deterministic, and backend-neutral. Its minimum contract
includes:

- schema/compiler/language version;
- source span and stable source-node identity;
- feature or operation kind;
- ordered dependencies and effect ordering;
- typed expressions and explicit units;
- selection/query expressions as structured IR;
- declared inputs and produced entity handles;
- opaque/unsupported regions with preserved source;
- native/custom capability decision and diagnostic provenance;
- canonical serialization and content hash.

Feature IR never contains DOM selectors, coordinates, pixels, Playwright calls,
REST endpoint names, or MCP tool names.

General FeatureScript cannot always be reduced to a linear list of root features.
Loops, conditions, helper functions, dynamic IDs/queries, and context effects must
remain opaque unless a compiler pass proves a safe representation.

### Model binding table

The compiler needs a persisted binding table between source semantics and applied
model state:

```text
FS Id/source node
  <-> Feature IR node
  <-> native feature id or Custom output
  <-> body/face/edge/query handle with provenance
```

This table supports dependency resolution, `qCreatedBy`-style semantics, Custom
body outputs, Native Boolean bridges, later selections, inspection, and safe
resume. It records a topology epoch or equivalent snapshot identity; stale entity
handles are never silently reused.

### Capability registry and partitioning

Native support is data-driven internal metadata, not one MCP tool per feature.
Each mapping declares:

- supported FS signatures and semantic guards;
- required selection strategies;
- native lowerer and driver compatibility;
- Custom fallback eligibility;
- postconditions and verification strength;
- mapping/fixture version and maturity;
- known unsupported and topology-sensitive cases.

Maturity remains:

```text
unsupported
  -> Custom-only
  -> Native experimental + Custom fallback
  -> Native preferred + Custom fallback
```

Partitioning operates on a dependency/effect graph, not only contiguous source
text. Initial releases may lower the entire exported feature through Custom even
when a smaller island is theoretically possible. Minimal opaque islands are an
optimization after closure and ABI correctness.

### Custom backend

The first Custom backend is whole-feature only. Required preconditions before
automatic use are:

- compiler-owned Feature Studio or other isolated source destination;
- deterministic names derived from plan/source hashes without collisions;
- exact target and existing-content inspection;
- source preimage and restore/retention policy;
- idempotent reuse of an already-applied identical plan;
- no duplicate feature insertion after an ambiguous result;
- namespace rules for IDs, helpers, imports, parameters, and generated features;
- declared body/value outputs and provenance for later native operations;
- explicit mutation plan and confirmation covering deployment, version creation,
  insertion, and any fallback.

A correct Custom path is a coverage strategy, not an unconditional guarantee.
Server compilation, browser state, policy, unsupported source boundaries, or
ambiguous prior mutations can still block it.

### Transaction IR and execution state

Transaction IR contains semantic browser actions, not improvised click sequences.
Each transaction declares:

- exact target and base-state fingerprint;
- preconditions and expected selection cardinality;
- ordered semantic actions;
- explicit commit point;
- postconditions and verification sources;
- idempotency classification;
- allowed retry phases and timeouts;
- compensation owned by this transaction;
- fallback eligibility and backend;
- driver/capability/plan versions;
- local evidence and checkpoint outputs.

Execution uses a durable state machine:

```text
planned
  -> applying_precommit
  -> commit_attempted
  -> applied_unverified
  -> verified
  -> compensated
  -> fallback_planned
  -> ambiguous | failed
```

Retry rules:

1. Read-only and proven-idempotent precommit actions may be retried within a hard
   bound.
2. A rejected action before the commit point may reset/cancel and use an allowed
   fallback.
3. After the commit attempt, observation failure is `ambiguous` until inspection
   proves whether the mutation exists.
4. An ambiguous mutation is never blindly retried and never followed by Custom
   fallback.
5. Undo/compensation is allowed only when the executor proves the affected change
   is compiler-owned and no intervening human/agent change would be reverted.
6. Custom fallback is allowed only before native commit or after verified
   compensation.

The existing project runner remains the orchestration and deliverable-acceptance
layer above this state machine. Its current checkpoints do not prove cloud rollback.

### Selection resolver

Selection is an independent subsystem whose input is structured Selection IR and
whose output is a cardinality-checked, provenance-bearing binding.

Initial strategy order:

1. unique compiler binding or native feature-tree identity;
2. unique named sketch, plane, part, or body;
3. Query Variable or FeatureScript-assisted semantic query;
4. deterministic viewport/highlight strategy;
5. vision-assisted or raw-coordinate recovery only at lower layers.

The minimal resolver kernel moves before the first Extrude PoC. Phase 4 Native
Extrude may support only one unique named sketch/profile and one unambiguous plane.
Zero or multiple matches fail before mutation.

### Inspector, verification, and export

Normalize observations into `ModelSnapshot` records containing backend,
timestamp, target IDs, coverage, confidence, and relevant state fingerprints.
Do not merge REST, DOM, and visual observations as if they had identical authority.

Verification is layered:

```text
transaction state
  + feature/model structure
  + geometry invariants with explicit units/tolerances
  + visual evidence when structure is insufficient
```

Native-vs-Custom equivalence should use the strongest affordable oracle for the
feature: feature tree, part/body count, bounding dimensions, volume/mass where
available, neutral export geometry, and bounded visual comparison. Exact topology
identity is not assumed unless the contract requires and proves it.

Export remains independently callable. A later Export Manager may choose a REST
or browser backend, but backend choice never bypasses quota, confirmation, or
artifact provenance rules.

## Public Agent surface

The steady-state public interface stays small and is conceptually staged:

1. offline check/compile;
2. inspect and bind an exact target;
3. produce an exact apply plan/dry-run;
4. confirmed apply of a plan hash;
5. verify/inspect;
6. screenshot/export.

A plan includes source/IR/driver/capability hashes, target/base token, expected
cloud and local mutations, possible fallback, estimated/max REST requests, and
stop conditions. Apply rejects a stale or altered plan.

Exact tool names and schemas are deferred until implementation. When introduced,
they must be derived into the existing catalog/reference system, use a bounded
compiler profile/surface, and deploy with the matching runtime prompt and client
companion generation. This roadmap must not become a hand-maintained tool schema.

## Fork and runtime isolation

Phase 0 must decide branch/worktree/separate-repository mechanics and produce an
isolation manifest covering:

- distinct MCP server identity and version generation;
- stable-line versus compiler-line tool/schema/prompt compatibility;
- browser profile and single-process ownership;
- browser config, outputs, diagnostics, and checkpoint roots;
- REST target state, credentials boundary, and quota ledger authority;
- bridge registration and process serialization where applicable;
- generated companion/reference revision and rollback unit;
- fixture/source provenance and redaction policy.

The stable and compiler MCP processes must not concurrently own the same browser
profile. If both lines can use the same Onshape account, live REST usage must be
serialized or use one authoritative shared accounting boundary so two ledgers
cannot independently overspend the account budget.

A compiler fork being available alongside the stable line does not mean both are
safe to run concurrently against the same target.

## Implementation phases

### Phase 0 - Baseline, correction, and isolation

Work:

- create the compiler fork/new line while retaining history;
- tag/snapshot stable server identity, public schemas, registry fingerprint,
  runtime prompt generation, browser FS deployment boundary, and relevant tests;
- produce REST endpoint-to-executable-handler coverage;
- produce the runtime isolation manifest;
- preserve stable behavior and define bug-fix propagation between lines.

Exit:

- the stable line remains runnable and unchanged by compiler experiments;
- compiler and stable state cannot collide accidentally;
- source-spec baseline discrepancies are recorded;
- no compiler behavior is claimed yet.

### Phase 1 - Internal ports and browser reclassification

Work:

- classify existing functions as B, C, or C2 without behavior changes;
- introduce compiler-facing browser-control, Custom-deploy, inspector, knowledge,
  and export ports;
- add a versioned browser driver identity and compatibility probe;
- retain public compatibility adapters where required;
- keep new native mappings internal.

Exit:

- existing offline regression remains green;
- compiler code can use mock ports without importing MCP/Playwright/credentials;
- current tools/list exposure and known-name compatibility are unchanged.

### Phase 2 - Frontend spike and stable IR

Work:

- select/pin or reject the community frontend based on recorded evidence;
- preserve `fs_local_check` as a separate preflight pass;
- implement versioned AST/diagnostics adapter;
- define Feature IR, Selection IR, OpaqueRegion, ModelBindingTable, capability
  registry, and canonical hashes;
- build golden fixtures for supported and unsupported language forms.

Exit:

- common feature-level calls and dependencies are recognized deterministically;
- ambiguous/unsupported semantics fail closed or remain opaque;
- no browser or live REST is needed for frontend regression.

### Phase 3 - Whole-feature Custom compiler MVP

Work:

- compile a complete exported feature into a compiler-owned Custom module;
- implement isolated naming, content/preimage checks, namespace/parameter/output
  ABI, idempotent plan reuse, and exact mutation planning;
- adapt the existing verified deploy/compile/insert workflow;
- separate offline compile, plan, confirmed apply, and verify.

Exit:

- the path is useful before native coverage exists;
- it cannot overwrite an arbitrary user Feature Studio;
- repeating an identical verified plan does not insert duplicate features;
- failure leaves auditable evidence and does not trigger unsafe cleanup.

### Phase 4 - Native Extrude proof with minimal selection

Work:

- implement the Transaction IR state machine and driver executor;
- implement the unique named sketch/plane selection subset;
- lower the same Feature IR to Native Extrude or whole-feature Custom;
- define preconditions, commit point, postconditions, compensation, and fallback;
- add structural, geometry, screenshot, and optional budgeted oracle fixtures.

Exit:

- browser selectors and locale details remain below Transaction IR;
- zero/multiple selection matches fail before mutation;
- precommit failure can use Custom fallback when planned;
- post-commit uncertainty becomes `ambiguous`, not automatic retry/fallback;
- Native and Custom outputs meet the declared equivalence tolerances.

### Phase 5 - Safe fallback and recovery

Work:

- exercise every transaction-state transition with injected failures;
- inspect after an uncertain commit before any further mutation;
- compensate only compiler-owned changes;
- resume from transaction-boundary checkpoints with plan/base verification;
- integrate transaction results into project-level manifests.

Exit:

- duplicate native/Custom application is prevented;
- stale plans and changed targets fail closed;
- retry, compensation, and fallback behavior is deterministic and evidenced.

### Phase 6 - Inspector, selection, Boolean bridge, and export

Work:

- formalize ModelSnapshot and observation provenance;
- extend selection strategies and topology-epoch invalidation;
- define body-output ABI and Native Boolean bridge;
- normalize screenshot/visual inputs and export orchestration;
- add Fillet/Chamfer only after their selection contracts are reliable.

Exit:

- compiler decisions consume normalized observations rather than raw DOM/REST
  payloads;
- body/query crossings have persisted bindings and invalidation rules;
- verification strength and unsupported evidence remain explicit.

### Phase 7 - Frequency-driven native coverage

Add native mappings in real project-frequency order. Each feature may ship
Custom-only before gaining experimental and then preferred Native support. Every
mapping includes semantic guards, driver compatibility, fallback policy,
postconditions, fixtures, and maturity evidence.

### Phase 8 - Sketch compiler

Introduce a separate canonical Sketch IR and a deliberately small supported UI
subset. Unsupported sketch behavior remains Custom-only. Do not block the general
hybrid architecture on complete interactive sketch reproduction.

### Phase 9 - Custom island extraction

Implement dependency/closure analysis, namespace rewriting, multiple-island ABI,
and opacity minimization only after whole-feature Custom and Native/Custom
boundaries are proven on real projects.

## Verification plan

All routine development verification remains offline with `LIVE_API_ENABLED`
unset.

| Change area | Minimum evidence |
|---|---|
| Frontend dependency | pinned provenance/license/version record; parser corpus; unsupported/version-negative cases |
| AST and Feature IR | golden fixtures, schema round trip, canonical hash, stable source spans, unknown fail-closed cases |
| Partitioner | dependency/effect graph cases; whole-feature Custom fallback; no unsafe island extraction |
| Custom backend | existing user source preserved; second output/island naming; compile failure; version reuse; duplicate plan; ambiguous insertion |
| Transaction engine | failure injection before/after every action; commit ambiguity; stale base; idempotent retry bounds; compensation ownership |
| Selection | zero/one/multiple matches; stale topology; partial selection reset; locale/driver variants |
| Native mapping | transaction postconditions; feature-tree/part state; unit/tolerance checks; Native-vs-Custom differential evidence |
| Inspector/export | provenance and coverage; target identity; artifact hashes; explicit units/coordinate frames |
| MCP surface | unique schema/handler names, catalog/profile integration, protocol-clean stdout, runtime-prompt/client compatibility |
| REST oracle | dry-run and mock/replay first; one explicit unresolved fact and hard live budget only when still necessary |
| Browser field evaluation | read-only selector/capability probe first; explicit target/mutations/stop conditions; no cloud mutation without confirmation |

No phase exit may be satisfied only by click completion, request construction,
process exit, a stale fixture, or an old field result. Formal verification must
state the candidate revision, environment, commands, fresh/cached evidence, and
uncovered scope.

## Explicit non-goals for the first compiler cycle

- replacing the REST client/reference architecture;
- exposing every compiler mapping or browser function as an MCP tool;
- implementing a complete local FeatureScript runtime or geometry kernel;
- arbitrary FS-to-native-tree decompilation;
- bidirectional cloud-model/local-FS synchronization;
- automatic retry after an ambiguous cloud mutation;
- automatic undo without compiler-owned mutation proof;
- minimal multi-island extraction before dependency closure exists;
- full Sketch lowering before the general dual-backend architecture works;
- private Onshape RPC or access-control reverse engineering;
- describing browser compilation primarily as an API-quota bypass.

## Open decisions and gates

The following are intentionally unresolved and must be decided with evidence:

1. fork form and state-isolation layout;
2. compiler package name and artifact storage root;
3. community frontend selection and language boundary;
4. exact initial FS compile-unit syntax;
5. base-state token available without hidden live REST;
6. compiler-owned Feature Studio/version retention policy;
7. first native feature if Extrude selection cannot meet the minimal resolver gate;
8. Native-vs-Custom geometry tolerances for each feature class;
9. release/policy conditions for the experimental browser compiler backend.

These unknowns do not block offline frontend/IR work, but the relevant gate must
close before cloud mutation or production-facing claims.

## Related documents

- Source proposal: `../../Onshape_MCP_FS_Hybrid_Compiler_Agent_Execution_Spec_v2.md`
- Current architecture: `../architecture/OVERVIEW.md`
- Development entry: `../development/START.md`
- Verification matrix: `../verification/MATRIX.md`
- Browser module contract: `../modules/browser-mode.md`
- REST module contract: `../modules/rest-api-mode.md`
- Documentation module contract: `../modules/onshape-docs.md`
- MCP module contract: `../modules/mcp-main.md`
- Dynamic exposure/native-modeling history: `DYNAMIC_TOOL_DISCOVERY.md`
- Existing FS browser semantics: `BROWSER_FS_SEMANTIC_TOOLS.md`
- Planned browser-tool registry: `BROWSER_PLANNED_TOOLS.md`

The source proposal remains useful design input. This roadmap is the repository-
integrated sequencing and safety interpretation; neither document represents an
implemented compiler until code, contracts, and matching verification exist.
