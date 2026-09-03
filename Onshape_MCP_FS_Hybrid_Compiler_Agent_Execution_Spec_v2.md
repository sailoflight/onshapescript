# Onshape MCP → FeatureScript Hybrid Compiler
## Agent Execution Specification v2

**Audience:** Agents actively developing the existing Onshape MCP repository.  
**Primary objective:** Push the existing project toward an FS-first hybrid compiler architecture without sacrificing the current usable implementation.  
**Migration policy:** Prefer a repository fork / new implementation line over forcing the existing production-capable project to satisfy the new architecture immediately.

---

# 0. Mandatory interpretation

Do **not** treat this document as a request to redesign the project from zero.

The current project already has substantial working infrastructure. The task is to **reuse, reclassify, and progressively compile over it**, not to rebuild equivalent foundations.

The target architecture intentionally breaks part of the old six-level semantic/tool organization. This is acceptable.

The following principle is authoritative:

> Existing code is an implementation asset, not an architectural constraint.

In particular:

- Do not preserve the six-level semantic model merely for conceptual purity.
- Do not keep a function Agent-visible merely because it was historically classified as L3-L6.
- Do not force FS compilation to conform to the old tool hierarchy.
- Do not rewrite proven REST or browser-FS deployment code unless required by an interface boundary.
- Do not require the new compiler fork to immediately replace the stable project.

Recommended repository strategy:

```text
existing onshape-mcp
    ├─ remain usable
    ├─ continue bug fixes if needed
    └─ serve as proven implementation/reference

fork: onshape-fs-compiler / equivalent
    ├─ freely restructure internals
    ├─ reuse existing REST/browser/runtime code
    ├─ may be temporarily incomplete
    └─ target the architecture defined below
```

The fork is allowed to prioritize architectural correctness over immediate end-user completeness because the original project remains available.

---

# 1. Current baseline: treat as completed assets

The following capabilities already exist and should be assumed available.

## 1.1 Complete public REST wrapper

Current state:

- Broad/complete intended coverage of Onshape Public REST API.
- Quota/rate accounting already exists.
- REST is an independent operating path.
- Official API documentation is available offline.
- An indexer is already used to locate the required API documentation/capability before returning the corresponding REST tool.

Existing workflow is correct and should remain:

```text
Agent request
    ↓
offline documentation/index search
    ↓
identify required REST operation
    ↓
expose/load only relevant REST tool
    ↓
execute
```

Do **not** replace this with hundreds of permanently visible REST tools.

Do **not** redesign the REST layer into the same abstraction used by the FS compiler.

REST remains valuable as:

1. official structured operation path;
2. read/inspection path;
3. compiler development oracle;
4. validation path when quota permits;
5. independent fallback for operations naturally suited to REST.

---

## 1.2 Complete browser FeatureScript deployment

Already available:

- browser-driven Feature Studio / FS deployment;
- local FS source transfer/update;
- ability to use browser execution instead of consuming REST quota for every source deployment;
- sufficient browser infrastructure to make FS deployment operational.

This capability is **not obsolete** under the target architecture.

It becomes a core compiler backend:

```text
unsupported / unstable native lowering
        ↓
Custom Feature FS fragment
        ↓
existing browser FS deployment
        ↓
working Onshape Custom Feature
```

Preserve this path aggressively because it gives the future compiler a correctness fallback before native UI coverage is complete.

---

## 1.3 Existing FS semantic checking

A certain amount of FS semantic validation already exists.

Extend it. Do not discard it.

Target evolution:

```text
current semantic checker
        +
community FeatureScript language-support parser/metadata
        +
compiler-specific semantic passes
        ↓
local FS frontend
```

The compiler should prefer refusing native lowering over guessing when semantic confidence is insufficient.

---

## 1.4 Existing six-level semantic system

Current project concept:

```text
L1 atomic browser operation, no semantics
L2 composed browser operation, no Onshape semantics
L3 atomic Onshape semantic operation
L4 composed Onshape operation
L5 complete Onshape operation
L6 reusable project-level Onshape operation
```

Keep this classification only where it remains useful for source organization, debugging, migration, or reuse.

It is **not** a target architecture requirement.

The new system explicitly allows:

```text
old L1/L2 → raw browser runtime
old L3-L6 → compiler browser library / recipes / tests / legacy compatibility
```

No requirement exists that a future FS compiler stage maps cleanly to one semantic level.

---

## 1.5 Offline official documentation + indexer

Already available:

- official REST documentation offline;
- official FS/developer documentation offline;
- indexing/search capability;
- capability discovery before tool exposure.

This is a major existing subsystem and should become the common **Knowledge Plane**.

Do not make Agents carry the full documentation context when the indexer can retrieve only relevant material.

Known limitation:

- human-facing UI tutorial/help material is not currently a complete indexed automation corpus.

Do not block the compiler on obtaining such a corpus. Build UI mappings incrementally through controlled observation, existing browser code, official help where available, REST comparison, and fixtures.

---

# 2. Target architecture

The project should stop converging toward “more MCP tools” and instead converge toward:

> **Agent writes FeatureScript → local FS frontend validates/understands it → compiler lowers it into browser transactions that create native root features when reliable → unsupported regions become deployable Custom Feature fragments.**

High-level topology:

```text
                               Agent
                     ┌───────────┴───────────┐
                     │                       │
             management / inspect          CAD intent
                     │                       │
                     │                   local .fs
                     │                       │
              ┌──────▼──────┐         ┌─────▼────────────┐
              │ A. REST     │         │ D. FS Frontend   │
              │ Mirror      │         │ + Hybrid Compiler│
              └──────┬──────┘         └─────┬────────────┘
                     │                      Feature IR
                     │                       │
                     │             ┌─────────┴──────────┐
                     │             │                    │
                     │       Native Lowering      Custom Lowering
                     │             │                    │
                     │      Transaction/UI IR      FS fragment/island
                     │             │                    │
                     │             │           existing FS deploy backend
                     │             │                    │
              ┌──────▼──────┐      └──────────┬─────────┘
              │ B. Browser  │                 │
              │ Control     │          ┌──────▼────────┐
              │ Plane       │          │ C2. Browser   │
              └──────┬──────┘          │ Compiler Lib  │
                     │                 └──────┬────────┘
                     └────────────┬───────────┘
                                  │
                           Onshape Web Client
                                  │
                           Onshape Cloud Model
                                  │
                       Native Root Feature Tree

Cross-cutting:
C  Raw browser rescue/debug runtime
E  Vision / screenshot / viewport
F  Export / file I/O
G  Inspector / verification / recovery
K  Offline knowledge/index/fixtures
```

---

# 3. Subsystem A - REST Mirror

## 3.1 Keep current architecture

Subsystem A remains a near-literal wrapper of the official Public REST API.

Do not over-abstract it into compiler semantics.

Expected pattern:

```text
official endpoint/schema
       ↓
thin wrapper
       ↓
auth + quota + error handling
       ↓
dynamic tool disclosure through indexer
```

## 3.2 REST is also the development oracle

During UI compiler development, REST should be used to inspect the server-side result of known UI actions whenever quota permits.

Example:

```text
create Extrude through UI
        ↓
REST read resulting feature
        ↓
capture feature representation
        ↓
compare with stdlib FS definition
        ↓
define FS ↔ Feature IR ↔ UI mapping
```

Build fixtures from this process rather than relying on memory or informal assumptions.

Recommended fixture structure:

```text
fixtures/features/
    extrude/
    fillet/
    chamfer/
    boolean/
    hole/
    pattern/
    sketch/
    ...
```

A fixture may contain:

- FS example;
- official REST representation;
- expected root feature result;
- UI field mapping;
- selection requirements;
- screenshots;
- known driver/version notes.

---

# 4. Subsystem B - Browser Control Plane

B contains **Onshape-level semantics that are not CAD modeling language semantics**.

Examples:

- document navigation;
- workspace/version navigation;
- create/open/rename/delete document elements;
- Part Studio / Feature Studio / Assembly tab management;
- page-level search;
- menus/toolbars where used for general control;
- document/page state;
- UI-only control operations;
- import/export UI navigation when required.

B may overlap REST. That is intentional.

REST and Browser Control Plane are separate operating paths with different strengths.

Do not push CAD modeling logic such as “make a leadscrew” into B.

---

# 5. Subsystem C - Raw Browser Rescue Runtime

Subsystem C should deliberately become **less semantic** than the current browser stack.

Target definition:

> C contains pure browser/computer-use operations with zero Onshape domain semantics.

Examples:

```text
click
move mouse
press key
type text
scroll
wait
query DOM/accessibility
read visible text
focus element
capture raw browser screenshot
coordinate click
open context menu
```

C is used for:

1. browser driver development;
2. diagnosing failed transactions;
3. exploring changed UI;
4. recovering from unexpected modal/state problems;
5. emergency manual completion when higher layers are unavailable.

### Visibility rule

C is **hidden by default**.

Only expose C temporarily for debugging/recovery/development.

C must never become the Agent's normal CAD interface.

---

# 6. Subsystem C2 - Full Onshape Browser Operation Library

C2 is different from C.

C2 contains the existing and future **Onshape-aware** browser operations used by the compiler backend.

Likely sources:

```text
existing L3
existing L4
existing L5
existing L6 where still reusable
new native feature UI workflows
new selection workflows
existing browser FS deployment workflows
```

Examples:

```text
open Onshape tool search
launch Extrude
focus a feature selection field
set an Onshape expression field
commit a feature dialog
create/update Feature Studio
create Query Variable
create native Boolean
activate Part Studio
```

Normal flow:

```text
Agent
  ↓
FS
  ↓
D compiler
  ↓
C2
  ↓
C / browser runtime as necessary
```

### Direct C2 exposure

Allowed only when useful for:

- compiler implementation;
- new feature mapping;
- regression diagnosis;
- semantic recovery;
- a rare operation that cannot yet be expressed through FS/compiler.

Expected steady state: direct Agent→C2 usage should be rare.

The project should not spend significant design effort making every C2 function pleasant as a public MCP tool. C2 is primarily an internal library.

---

# 7. Subsystem D - FS Frontend + Hybrid Compiler

D is the new project's primary architectural focus.

## 7.1 Agent-facing modeling workflow

Normal CAD workflow should become:

```text
Agent writes FS
      ↓
local syntax/semantic checks
      ↓
Agent fixes FS until acceptable
      ↓
compiler parses/analyzes FS
      ↓
Feature IR
      ↓
partition + lowering
      ↓
transaction stream and/or Custom Feature fragments
      ↓
apply to Onshape
      ↓
verify
```

The Agent should normally **not** call individual Extrude/Fillet/browser tools.

FS is the modeling language.

---

## 7.2 Reuse community FeatureScript language support

Investigate and reuse the 2026 community FeatureScript language-support implementation rather than writing a parser from zero.

Treat it as:

- parser/frontend seed;
- symbol source;
- stdlib symbol metadata source;
- feature parameter/precondition metadata source;
- local code analysis infrastructure.

Do **not** assume it is a complete FeatureScript compiler.

The existing project is intentionally partial/tolerant and does not reproduce Onshape's complete runtime/type system.

That is acceptable because this project does not need to execute the Onshape geometry kernel locally.

Required local capability is only:

```text
parse enough
resolve enough
validate enough
classify enough
lower enough
```

Actual geometric execution remains in Onshape.

---

## 7.3 Preserve and strengthen existing semantic checks

Merge existing semantic checking with the new frontend rather than replacing it blindly.

Compiler confidence policy:

```text
high confidence native semantics
        → native lowering permitted

valid FS but unsupported/ambiguous lowering
        → Custom Feature lowering

semantic uncertainty likely to change behavior
        → reject/ask Agent to repair FS
```

Never invent native UI semantics from an uncertain parse merely to maximize native feature count.

---

# 8. Feature IR - stable compiler boundary

Do not compile directly from FS source to browser operations.

Create a stable Feature IR.

Example source:

```fs
extrude(context, id + "body", {
    "entities" : profile,
    "endBound" : BoundingType.BLIND,
    "depth" : 8 * millimeter
});
```

Conceptual IR:

```text
FeatureIR {
    type: EXTRUDE
    id: body
    dependencies: ...
    selections:
        entities: SelectionExpression(profile)
    parameters:
        endBound: BLIND
        depth: Expression("8 * millimeter")
}
```

Feature IR must not contain:

- DOM selectors;
- browser coordinates;
- Playwright implementation details;
- screenshot pixels;
- REST endpoint names.

FS frontend and browser runtime must meet at IR boundaries, not by leaking implementation details across layers.

---

# 9. Dual backend requirement for FS capabilities

This is a core design rule.

For every important FS construct/feature, support two possible lowering modes over time:

```text
                  Feature IR
                      │
          ┌───────────┴───────────┐
          │                       │
 Native UI implementation   Custom FS implementation
          │                       │
 native root feature        Custom Feature fragment/island
```

The two implementations have different purposes.

## 9.1 Custom FS implementation - coverage/reliability path

This should usually be implemented **first** when it can reuse the existing deployment backend.

Advantages:

- fastest route to working behavior;
- leverages already-proven browser FS deployment;
- supports complex FS naturally;
- protects the overall system if native UI automation breaks;
- allows architecture development without waiting for complete UI mapping.

Custom lowering is the primary correctness fallback.

## 9.2 Native UI implementation - quality/editability path

Native lowering converts a Feature IR operation into browser transactions that cause Onshape to create ordinary root features.

Advantages:

- human-editable native feature tree;
- ordinary Onshape modeling semantics;
- better manual intervention;
- avoids collapsing an entire design into one Custom Feature.

Costs:

- UI mapping;
- selection/picking;
- driver maintenance;
- higher implementation complexity.

## 9.3 Required maturity model

A feature may progress through:

```text
unsupported
    ↓
Custom-only
    ↓
Native experimental + Custom fallback
    ↓
Native preferred + Custom fallback
```

Do not require Native support before considering the feature supported.

This is the key mechanism that allows the new fork to advance quickly without becoming unusable.

---

# 10. Compiler partitioning and Custom Feature islands

The compiler should minimize opaque regions.

Example:

```text
A native-capable
B native-capable
C unsupported
D unsupported
E native-capable
```

Prefer:

```text
A Native
B Native
Custom(C,D)
E Native
```

not:

```text
Custom(A,B,C,D,E)
```

Compiler objective:

> **Minimize opaque feature span while preserving reliable semantics.**

Native lowering is an optimization. Custom lowering guarantees coverage.

---

# 11. Body ABI + Native Boolean bridge

For complex FS regions that mainly generate geometry, prefer:

```text
Custom Feature
      ↓
tool body / bodies
      ↓
Native Boolean ADD / REMOVE / INTERSECT
      ↓
native model continues
```

Example:

```text
Extrude Main Body       Native
Complex Vent Cutter     Custom
Boolean REMOVE          Native
Fillet                  Native
```

Recommended Custom Island boundary values:

```text
primitive parameters
queries/reference geometry
coordinate frame / plane
body inputs
        ↓
Custom Feature
        ↓
one or more bodies
```

Prefer Body crossings over fragile edge/face topology crossings when practical.

Boolean is not universal. Operations that intrinsically depend on topology mutation or special face/edge behavior may remain opaque Custom Features.

---

# 12. Transaction IR / UI IR

Native lowering should not generate improvised click sequences.

Compile Feature IR to a transaction representation.

Example:

```text
Transaction CREATE_EXTRUDE

preconditions:
  active element = expected Part Studio
  no conflicting modal

operations:
  open_tool(EXTRUDE)
  bind_selection(profile)
  set_field(endBound, BLIND)
  set_expression(depth, "8 mm")
  commit()

postconditions:
  native Extrude root feature exists
  expected model change observed

recovery:
  cancel dialog
  undo partial state if required
  reset UI state
  retry deterministic path
  fallback to Custom implementation
```

The transaction layer is the correct home for:

- retries;
- rollback;
- logging;
- timing/wait state;
- browser-driver versioning;
- regression fixtures;
- backend fallback.

Do not let Feature IR call DOM primitives directly.

---

# 13. Browser driver is a versioned backend

Onshape UI is not a stable public automation ABI.

Required separation:

```text
FS
 ↓
Feature IR
 ↓
Transaction/UI IR
 ↓
version-specific Browser Driver
 ↓
C2 / C
 ↓
Onshape UI
```

If Onshape changes DOM/tool placement:

```text
FS frontend      unchanged
Feature IR       unchanged
partition logic  unchanged
transaction IR   mostly unchanged
Browser Driver   patched
```

Never embed raw DOM/CSS assumptions into the FS compiler semantic layer.

---

# 14. Selection Resolver

Selection is expected to be the hardest native-lowering problem.

Treat it as an independent subsystem.

Input:

```text
SelectionExpression / FS Query semantics
```

Output:

```text
actual Onshape UI selection
```

Possible strategies, in increasing fallback order:

```text
1. named feature/tree object selection
2. part/sketch/plane semantic selection
3. Query Variable
4. FeatureScript geometric query assistance
5. Create Selection expansion
6. deterministic viewport + highlight
7. vision-assisted picking
8. raw coordinate/pixel fallback
```

The Agent continues to express semantic queries in FS.

Pixel decisions belong below the compiler boundary.

---

# 15. Sketch is a separate lowering problem

Do not block D on perfect Sketch support.

Sketch interaction differs from ordinary feature dialogs because human UI behavior includes:

- inferred constraints;
- cursor interaction;
- snapping;
- region behavior;
- interactive construction.

Use:

```text
FS Sketch AST
      ↓
Canonical Sketch IR
      ↓
Sketch UI Lowerer
```

Initial supported subset can be intentionally small:

```text
line
rectangle
circle
arc
point
coincident
horizontal/vertical
parallel/perpendicular
basic dimensions
```

Unsupported sketch behavior may initially remain inside Custom Feature fallback.

---

# 16. Subsystem E - Vision / screenshot / viewport

Vision is a first-class horizontal subsystem, not only an emergency picking tool.

Required capabilities should include at least:

## 16.1 UI observation

```text
browser screenshot
modal/dialog screenshot
error-state screenshot
menu/toolbar screenshot
```

## 16.2 CAD viewport observation

```text
model screenshot
fit model
known isometric/front/top/right view
zoom control
isolate/hide
selection highlight capture
```

## 16.3 Uses

- compiler verification;
- selection fallback;
- visual regression;
- diagnosing UI-driver failure;
- Agent inspection of final geometry.

The compiler should prefer structured verification when available, but visual verification is required for failures that structure alone cannot expose.

---

# 17. Subsystem F - Export / file I/O

Export is an independent high-level capability, not just a browser macro.

Required intents include:

```text
export_part
export_partstudio
export_assembly
```

Common formats:

```text
STEP
Parasolid
STL
3MF
OBJ / glTF where useful
other supported formats as needed
```

Backend selection:

```text
Export Manager
    ├─ REST backend
    └─ Browser backend
```

Prefer REST when appropriate and quota-efficient. Use browser export where UI behavior is required or REST is unsuitable.

Target end-to-end pipeline:

```text
Agent writes FS
→ compile/apply
→ verify
→ capture screenshot
→ export STEP
→ export STL/3MF if requested
```

---

# 18. Subsystem G - Inspector / verification / recovery

## 18.1 Inspector

Provide a unified way to inspect current model/application state using the best available backend.

Useful state includes:

- active document/workspace/element;
- feature tree names/types;
- parts/bodies;
- variables;
- bounding boxes;
- regeneration/error state;
- mass properties where useful;
- current dialog/selection state;
- screenshots.

REST and Browser observations may both contribute.

## 18.2 Verification

Do not treat “browser transaction finished” as success.

Prefer layered verification:

```text
transaction state
+
model/feature structural state
+
geometry checks
+
visual check when useful
```

## 18.3 Recovery ladder

Recommended order:

```text
native transaction fails
    ↓
cancel/reset local UI state
    ↓
retry deterministic native strategy
    ↓
rollback/undo if needed
    ↓
Custom FS fallback
    ↓
C2 direct semantic recovery
    ↓
C raw browser diagnosis
```

This ladder is a major reason to preserve existing working browser code even after D becomes primary.

---

# 19. Subsystem K - Knowledge Plane

Unify existing knowledge assets rather than introducing another documentation mechanism.

```text
K
├─ offline REST docs/index
├─ offline FS/developer docs/index
├─ stdlib symbols/metadata
├─ community language-support frontend data
├─ compiler feature fixtures
├─ browser transaction fixtures
└─ curated UI behavior notes where required
```

Agent lookup policy should remain progressive:

```text
search index first
→ retrieve only relevant docs/capabilities
→ execute
```

Do not preload complete official docs into Agent context.

---

# 20. Agent/tool exposure policy

Hard rule:

> **Internal capability count may grow without limit; always-visible Agent tool count must stay small.**

Likely internal future state:

```text
100+ REST wrappers
300+ browser/runtime functions
many native feature mappings
multiple selection strategies
vision/export/recovery operations
```

This is acceptable.

Normal Agent-visible surface should remain approximately:

```text
knowledge/index lookup
selected REST operations
small Browser Control Plane
FS workspace/edit/check
compile/apply/verify
inspect/screenshot
export
```

C is hidden.

C2 is hidden.

Native feature browser implementations are compiler backend code, not Agent tools.

---

# 21. Relationship to the old six-level system

The six-level model should not be deleted blindly, but it should lose architectural authority.

Recommended migration rule:

```text
L1/L2
  → usually C / low-level runtime

L3/L4/L5
  → usually C2 / transaction implementation

L6
  → evaluate individually:
       useful project recipe → keep as reusable implementation/test asset
       redundant with FS → stop exposing / deprecate
```

Do not force D to call one L5 operation because “L5 is the correct semantic level.”

If the clean implementation is:

```text
Feature IR
→ transaction recipe
→ several old L3/L4 functions
```

use that.

If the clean implementation bypasses an old semantic wrapper entirely, allow that.

The fork exists specifically so architecture can improve without preserving old layering assumptions.

---

# 22. Source-of-truth policy

Do not immediately define local `.fs` as the sole permanent source of truth for a complete Part Studio.

Otherwise:

```text
local FS → compile → cloud
human edits cloud model
local FS becomes stale
```

This introduces bidirectional synchronization/merge before the compiler itself is mature.

Initial policy:

> **Onshape remains authoritative live CAD state; FS is the Agent's modeling/patch language.**

Typical flow:

```text
inspect current Onshape state
       ↓
Agent writes FS program/patch
       ↓
compile/apply
       ↓
cloud model becomes new current truth
```

Full Part Studio ↔ FS round-trip/source synchronization is later research only.

---

# 23. Fork and migration strategy

The safest development strategy is to fork the working project before deep compiler restructuring.

## 23.1 Stable line

Keep current project usable:

```text
REST
existing indexer
browser FS deployment
current semantic checks
existing browser tools
existing six-level registry
```

Only necessary maintenance is required.

## 23.2 Compiler fork

The fork is free to:

- reorganize modules;
- hide/deprecate old tools;
- extract C/C2;
- introduce Feature IR and Transaction IR;
- vendor/fork the community FS frontend;
- add compiler-specific semantic passes;
- make Custom Feature the initial fallback for many operations;
- temporarily support fewer direct Agent workflows than the original project;
- break old internal semantic layering if doing so improves the compiler architecture.

The new fork does **not** need to be immediately production-complete.

The success criterion is architectural convergence while retaining the old repository as a usable fallback.

---

# 24. Implementation order based on current progress

Do not spend time rebuilding what already exists.

## Phase 0 - Fork and freeze interfaces

Immediately:

1. fork the current repository;
2. record the existing REST interface boundary;
3. record existing browser FS deployment boundary;
4. snapshot current L1-L6 registry;
5. preserve existing tests/fixtures;
6. ensure the old project remains usable.

No major rewrite yet.

---

## Phase 1 - Reclassify current browser code into C / C2

Goal is classification, not functionality changes.

- Move/mark pure browser operations as C.
- Move/mark Onshape-aware operations as C2.
- Keep compatibility adapters where needed.
- Stop assuming L-level = public Agent tool.
- Default C/C2 to hidden in the compiler fork.

Exit condition:

```text
existing browser behavior still works
but browser runtime is no longer conceptually the Agent CAD interface
```

---

## Phase 2 - Build FS frontend on current semantic checker + community language support

Tasks:

1. inspect/fork/vendor useful parser and metadata code;
2. reuse stdlib symbol/metadata generation;
3. merge with current semantic checks;
4. define AST/semantic contracts required by lowering;
5. add compiler-specific diagnostics only where necessary.

Do not attempt full Onshape runtime reimplementation.

Exit condition:

```text
common standard feature calls can be identified locally
with parameters/dependencies/selections represented reliably enough for lowering
```

---

## Phase 3 - Define Feature IR and Transaction IR

Implement stable data contracts before broad native UI support.

Minimum Feature IR:

- feature type;
- id/dependency;
- expressions/parameters;
- selections/query expressions;
- source span;
- lowering capability status.

Minimum transaction IR:

- preconditions;
- semantic browser actions;
- expected postconditions;
- recovery path;
- fallback backend.

---

## Phase 4 - Make Custom lowering a first-class compiler backend

Do this early because the browser FS deployment path already works.

Target:

```text
FS input
→ frontend
→ Feature IR
→ unsupported/native-not-ready region
→ deployable FS fragment
→ existing deployment backend
→ working Custom Feature
```

This proves D can produce useful output before native UI lowering becomes broad.

---

## Phase 5 - Native lowering PoC for one simple standard feature

Recommended first target: Extrude or another feature with simple dialog semantics.

Required dual path:

```text
same Feature IR
  ├─ Native UI implementation
  └─ Custom fallback
```

Verify native path using:

- feature tree;
- structural inspection;
- screenshot;
- REST comparison where quota is reasonable.

This is the critical proof that FS can become the Agent modeling language while producing root native features.

---

## Phase 6 - Add automatic fallback/recovery

Native failure must not become system failure.

Implement:

```text
native transaction
→ failure detection
→ rollback/reset
→ Custom FS implementation
→ verification
```

Only after this exists should native coverage expand aggressively.

---

## Phase 7 - Selection Resolver + Fillet/Chamfer class features

Use a feature where geometry selection is the primary difficulty.

Implement strategy ladder progressively rather than solving general vision picking first.

---

## Phase 8 - Formalize Vision + Inspector + Export

Integrate already available/raw screenshot functions into formal subsystem E/G interfaces.

Provide stable high-level operations for:

- deterministic model capture;
- visual verification;
- highlighted selection capture;
- STEP/STL/3MF export;
- model state inspection.

---

## Phase 9 - Expand native feature coverage by real project frequency

Do **not** reproduce the toolbar in arbitrary order.

Prefer features encountered frequently in actual Onshape work.

Example probable sequence:

```text
Extrude
Boolean
Fillet
Chamfer
Pattern
Hole
Shell
Revolve
Sweep
Loft
...
```

Every new feature may ship Custom-only first, then gain Native lowering later.

---

## Phase 10 - Sketch compiler

Treat separately after the general compiler/fallback architecture is proven.

---

## Phase 11 - Advanced Custom Island extraction

Only implement sophisticated dependency/closure analysis after real examples justify it.

Do not block early compiler usefulness on perfect minimal-island extraction.

---

# 25. Development rules

Agents modifying the fork should obey the following rules.

## Rule 1 - Reuse before rewrite

Before implementing any REST/browser/FS capability, search the current repository and Knowledge Plane for an existing implementation.

## Rule 2 - Existing usability must survive somewhere

It is acceptable for the compiler fork to be incomplete, but the original project must remain available as a working fallback during migration.

## Rule 3 - Do not preserve old layers at the expense of D

The six-level semantic system is not allowed to force an unnatural FS compiler design.

## Rule 4 - Prefer Custom fallback to speculative Native lowering

Wrong native semantics are worse than a correct Custom Feature.

## Rule 5 - Native lowering must be reversible

Every native transaction needs explicit failure detection and recovery/fallback behavior.

## Rule 6 - Browser details stay below Transaction IR

No DOM selector, pixel coordinate, or raw event sequence belongs in Feature IR or FS semantic analysis.

## Rule 7 - Selection is semantic above the resolver

Agents/compiler passes express what entity is wanted; the resolver decides how to obtain the actual UI selection.

## Rule 8 - Keep C and C2 available but normally hidden

They are essential engineering escape hatches, not normal Agent interfaces.

## Rule 9 - Tool count is not a public interface goal

Internal functions may grow freely. Do not expose them merely because they exist.

## Rule 10 - Build fixtures while reverse-mapping UI

Every newly supported native feature should leave behind enough data to reproduce/debug the mapping later.

---

# 26. Explicit non-goals for the current development cycle

Do not build now:

1. a replacement REST layer;
2. a second 300-tool public browser interface;
3. a full local FeatureScript geometry runtime/kernel;
4. perfect arbitrary-FS → native-tree decompilation;
5. full bidirectional cloud-model ↔ local-FS synchronization;
6. a vision-only CAD agent;
7. a requirement that every old L6 workflow survive unchanged in the compiler fork;
8. private Onshape RPC reproduction as a normal backend;
9. perfect Sketch lowering before the hybrid compiler is useful.

---

# 27. Minimum long-term Agent surface

The desired steady-state interface is conceptually small.

Agent normally needs:

```text
Knowledge/index search
Selected REST operations
Small Browser Control Plane
Local FS workspace/edit/check
Compile/apply/verify
Inspect/screenshot
Export
```

Agent normally does **not** need:

```text
raw click tools
native Extrude browser tool
native Fillet browser tool
selection implementation tools
browser FS deployment internals
old L3-L6 inventory
```

Those remain runtime/compiler assets.

---

# 28. Compliance note

Keep this issue visible but do not let it dominate implementation architecture.

Onshape's public terms contain broad restrictions on automated access, while historical official forum guidance has been favorable to keyboard/mouse automation of a user's own model. Browser automation should therefore remain an experimental/controlled backend until the intended usage receives sufficient policy confidence. In particular, do not describe or design the browser compiler primarily as an API-quota-bypass mechanism, and avoid private RPC/access-control reverse engineering.

This is a release/deployment constraint, not a reason to stop the technical fork or compiler PoC.

---

# 29. Target end state

The intended project should eventually behave as follows:

```text
Agent decides CAD change
        ↓
Agent writes ordinary FeatureScript
        ↓
local FS frontend validates/analyzes it
        ↓
Feature IR
        ↓
compiler partitions the program
        ↓
┌──────────────────────────────┐
│ native-capable region        │
│ → Transaction IR             │
│ → C2 browser runtime         │
│ → native root features       │
├──────────────────────────────┤
│ unsupported/unstable region  │
│ → FS fragment/island         │
│ → existing FS deploy backend │
│ → Custom Feature             │
└──────────────────────────────┘
        ↓
optional Native Boolean bridge
        ↓
Inspector + structural verification
        ↓
Vision verification if useful
        ↓
export if requested
```

At that point:

- REST remains complete and independently useful;
- browser FS deployment remains a reliability backend;
- the old six-level system survives only where useful as implementation infrastructure;
- C exists as a zero-semantic rescue layer;
- C2 contains the full semantic browser runtime but is rarely Agent-visible;
- FeatureScript becomes the primary Agent CAD language;
- Native UI lowering improves editability progressively without being required for correctness;
- Custom Feature lowering guarantees early coverage and resilience;
- internal capability count can grow substantially without forcing equivalent Agent context growth.

---

# 30. Immediate instruction to the development Agents

Start from the existing repository, not from a blank design.

**First action:** create a fork/new development line and freeze the current usable project as the fallback/reference implementation.

Then, in order:

```text
1. classify existing browser code into C and C2 without breaking behavior;
2. extract/reuse community FS parser + stdlib metadata alongside current semantic checks;
3. define Feature IR and Transaction IR;
4. make existing FS deployment callable as the compiler's Custom fallback backend;
5. compile one simple standard FS feature into a native root feature through Browser UI;
6. add automatic native→Custom fallback;
7. only then expand Selection, Vision, Sketch, and broad native feature coverage.
```

Do not optimize for immediate parity with the old tool inventory.

Optimize for establishing the new compilation architecture while keeping the old project available whenever the fork is incomplete.
