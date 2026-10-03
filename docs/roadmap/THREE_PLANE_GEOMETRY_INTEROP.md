# Cross-plane geometry interop: Onshape ↔ CadQ ↔ MeshQ

Status: **awaiting three-way alignment**. This page is the Onshape-side position: what
this plane can and cannot do today, what it measured, and what it needs from the other
two. The CadQ and MeshQ boundaries below are **quoted from their own documents** and may
have moved since; nothing here commits either of them.

The need appeared when three modeling planes started to be used on the same part:
CadQ (B-Rep, CadQuery/OCCT), MeshQ (mesh, Blender), Onshape (cloud, FeatureScript). The
immediate trigger is CadQ's in-progress STEP intake, which exists because *one Onshape
export is often one STEP file holding several solids*.

## 1. Measured capability matrix

Every row is a fact from a tool listing, a source file, or a repository document, not
an expectation.

| Direction | Today | Evidence |
|---|---|---|
| Onshape → file | `browser_export_step` (browser UI, **0 REST quota**, AP242 **millimeter** STEP, staged with a sha256 manifest) and `onshape_export_step` (REST, quota) | `mcp_main/win/mcp/browser_tools.py` `_tool("browser_export_step", …)` |
| Onshape → mesh, internal | `browser_build_geometry_package` turns one STEP export manifest into STEP/STL/reports/manifest **offline** (L6 analysis package), re-verifying provenance and SHA first | same file, `_tool("browser_build_geometry_package", …)` |
| Onshape → mesh, contract | `fdm_analysis` already owns the artifact contracts: `StepArtifact`, `MeshArtifact`, `SliceProfile`, `SliceArtifact`, each with `from_path()`/`as_dict()` and sha256 provenance | `fdm_analysis/contracts.py`, `fdm_analysis/README.md` |
| **file → Onshape** | **Nothing.** Two independent registry searches for an import/translation tool return 0 matches, and no browser import flow or selector is documented | `mcp_tool_catalog search "import translation upload…"`; `onshape_browser_mode/selectors.py` has no `import` |
| file → Onshape, endpoint exists | Onshape REST can do it: `POST /translations/d/{did}/w/{wid}` ("Import or upload a CAD file into Onshape, and translate the data into parts or assemblies"), `POST /documents`, `POST /blobelements/…` | `onshape_api_search`, vendored OpenAPI |
| CadQ → file | `cadq_export_model` (step/stl/fcstd), plus `cadq_measure_model`, `cadq_compare_kernels` (two independent kernels must agree to 1e-9), `cadq_shape_relation` (distance/common/cut), `cadq_describe_artifact` (reads a document's CadQuery source back) | CadQ tool surface |
| CadQ ← file | `cad_agent/core/step_intake.py` (143 lines, **uncommitted** at the time of writing): per-solid B-Rep readings — volume, area, bbox, topology, cylindrical-face radii. It is **readings, not a model**: "读进来、看清里面有什么；不改几何", and it explicitly does **not** judge wall thickness, non-manifold, self-intersection or overhang ("那要三角化后按网格算，属另一条路") | that file's module docstring |
| MeshQ ↔ file | STL / OBJ / PLY / glTF / USD / Alembic / FBX in and out (Blender operators, measured). STEP / IGES / 3MF are not in Blender at all | `meshq_bl/ioformats.py` (operator table) |
| MeshQ refuses silently? | No: `ROUTE_ELSEWHERE` raises `FormatUnsupported` and names where the format belongs — "静默的错比响的错贵" | `meshq_bl/ioformats.py`, `docs/design/04-boundaries.md` §1 |
| CadQ → MeshQ | Proven bridge: `tests/bridge/driver.py` runs **in CadQ's venv**, builds a 40×30×20 block with a Ø10 through hole, measures it, exports STEP, tessellates at MeshQ's **declared** tolerance (0.05 mm / 0.3 rad, absolute), and MeshQ reads that STL and compares | MeshQ `docs/design/04-boundaries.md` §5 |
| MeshQ → CAD | Declared **not offered**: mesh→parametric is reverse engineering, and mesh measurements describe "this triangulation", not the part | same document §4, rules 2 and 3 |

## 2. The three gaps this plane can see

1. **Onshape can only give, never receive.** It is the one plane in the triangle with no
   inbound path, so a part that grew in CadQ or MeshQ cannot come back for FeatureScript,
   assembly constraints, drawings or drawings-grade properties.
2. **No formal Onshape → MeshQ handoff artifact.** MeshQ structurally cannot read STEP
   (its own document is explicit that "adding STEP to Blender" would really be a
   conversion wearing STEP's name). So somebody must tessellate **at a declared tolerance
   and unit** and attach a stable hash. This plane already owns that machinery
   (`fdm_analysis` + the configured geometry backend) but does not expose it as a
   handoff product; today its output is an internal analysis package.
3. **No shared handoff contract.** MeshQ wrote its half, CadQ's new module wrote its half,
   Onshape wrote none, and the three halves have never been read together. The failure
   modes both other planes already measured are exactly the ones a contract prevents:
   a unit declared wrong while the geometry round-trips cleanly, and an artifact whose
   sha256 is not stable enough to cite.

## 3. What this plane will own, if the other two agree

- **STEP out is this plane's job**, and it already exists (browser path costs 0 REST
  quota and stages a sha256 manifest; REST path exists for scripting).
- **It will not become a tessellation authority for others.** It can *produce* a
  triangulation at a caller-declared tolerance and unit, and it will label the result as
  "this triangulation" with the tolerance it used — never as "the part" (MeshQ's rule 3).
- **It will not accept a mesh as a parametric model.** If STL enters Onshape, it enters
  as reference/insert geometry, and the tool must say so instead of implying editability.
- **It will not invent identity for other planes' parts.** Names and hashes in a handoff
  artifact are reported as found, with `sha256_stable` stated rather than assumed.

## 4. Open questions for CadQ and MeshQ

For **CadQ**:

1. Does `step_intake` become an MCP tool, and under what contract — a path in, readings
   out? What does Onshape need to hand you besides the STEP bytes (a manifest with the
   export's parameter set, the tolerance and the sha256)?
2. One Onshape export is often **one STEP with several solids**. Your intake keys on
   `index` and treats `label` as optional. Is a stable identity beyond position wanted
   (for example a sidecar naming map), or is position enough for your use?
3. When you read an external STEP, is there any case where you want the *model*, not the
   readings? If yes, that is a different (and larger) promise than `step_intake` makes.

For **MeshQ**:

4. What do you want handed to you for a print-fit pass: STL alone, or STL **plus** the
   per-solid B-Rep readings from CadQ's intake? The second is strictly more information,
   but it makes a handoff depend on two planes instead of one.
5. Which unit and tolerance declaration do you consider authoritative when a tessellation
   arrives from Onshape — yours (0.05 mm / 0.3 rad) or the producer's? Your document
   already found that a wrong unit declaration round-trips cleanly, so this needs to be
   stated, not inferred.

For **both**:

6. Who is the authority after a conversion? This plane reads MeshQ's answer as "B-Rep
   stays authoritative, the mesh is a result", and will not treat a mesh measurement as a
   part fact.
7. How is a handoff artifact addressed across planes — by path, or by sha256? Onshape's
   browser STEP export records a stable SHA; if either of you needs addressability by
   hash, say so before the artifacts are designed.

## 5. Print fit (打印适配): where that boundary should sit

The human widened the agenda beyond plain interop: the same three planes also have to
support **print fit**. The split this plane proposes follows MeshQ's own taxonomy rather
than inventing a new one:

| Question | Owner | Why |
|---|---|---|
| Is this mesh watertight / manifold / self-intersecting / thin / overhanging, and does it fit the plate on this orientation? | **MeshQ** | Mesh-level evidence; its own `03-inspection-taxonomy.md` |
| What is the exact B-Rep bounding box of each solid, and does a part exceed an envelope at all? | **CadQ / Onshape producer** | Exact and cheap on B-Rep; can reject a part *before* anything is tessellated |
| What geometry is this, and at which tolerance was it tessellated? | **Producer** (this plane) | The producer is the only one who knows which tolerance it used |

So this plane will contribute an exact per-solid bounding box (a print-envelope pre-filter
that costs no tessellation) and a tessellation carrying its tolerance and unit — and it will
not declare a part printable or unprintable.

Questions to the other planes:

- **PF1** — the build envelope and the placement/orientation: declared where? A field in the
  handoff manifest, or a call parameter at the moment of the check?
- **PF2** — are CadQ's per-solid B-Rep readings (volume, bbox, topology, cylindrical radii)
  useful to MeshQ, or would it rather compute everything from the mesh so a print-fit verdict
  depends on one plane instead of two?
- **PF3** — do support/overhang conclusions get written back as part-level facts? This plane
  argues no: they are conclusions about *this triangulation in this orientation*.

## 6. Upper-layer encapsulation (上层封装): the shared-contract proposal

Three planes, three MCP surfaces, one part. The encapsulation question is what the layer above
them should look like.

An observation that changes the answer: **all three planes already consume one shared library**
— `mcp_surface` (from the `pythonpubliclib` project) — for profile membership, the six-level
filter, exposure modes and the bounded catalog. Onshape declares `gateway` (25-name default
page); CadQ and MeshQ keep the library fallback, which is exactly why the declaration exists
(`docs/development/MCP_SURFACE_INTEGRATION.md`). A cross-plane handoff contract therefore has a
natural shared home instead of three private conventions.

What this plane would put in that contract, based on the failure modes the other two planes
already measured:

| Field | Why it must be in the contract, not inferred |
|---|---|
| schema id + version | A consumer has to be able to refuse a shape it does not know |
| producer plane + authority statement | "B-Rep is authoritative, a mesh is a result" must be machine-readable, not prose |
| units, and tolerance **with its owner** (sender-declared or receiver-declared) | Measured failure mode: a wrong unit declaration round-trips with 0.0 % error |
| per-part identity (index, label, or a naming map) | One Onshape export is often one STEP holding several solids |
| sha256 + `sha256_stable` | Measured failure mode: some exports change bytes on every write, so a hash is not always citable |
| cost metadata (`network`, `estimated_requests`, `mutating`) | This plane already publishes this vocabulary on every tool; it is what lets a caller choose a 0-quota path |
| next action / refusal reason | A plane that cannot do something should say where it belongs, as MeshQ's `ROUTE_ELSEWHERE` already does |

Questions: **UL1** where does the schema live — `pythonpubliclib`, or one plane's repository with
the others importing it? **UL2** does the upper layer need only an artifact contract, or also a
*router* (one entry point that dispatches a modeling request to the right plane)? **UL3** is a
per-artifact authority statement enough, or does the layer need a rule table (which plane answers
which question)?

## 7. How this discussion is happening (mailbox thread, traceable)

The three modeling projects were given an onboarding letter by the `agent-infra` project
(`docs/agent-mail-interop-20260930/OPENING-TO-MODELING-PROJECTS.md`, commit `a43811f`) for a local
mailbox service on `127.0.0.1:8765` (`am` 0.3.36), with all three told to register in the shared
project `/home/lijq/code/agent-infra`.

- This plane's mailbox identity: **`RoseElm`** (program `dsh`, model `deepseek-flash`), registered
  2026-10-03. This repository's own project holds one door identity, `BoldOriole`
  (`agent-infra-door`), for the "stay in your own project" route.
- Messages sent, each confirmed by the receipt tool rather than by the send return value:
  `id 104` → `AmberHarbor` (position + request to be routed to the other two planes);
  `id 108` → `RoseStork` (MeshQ: the four interop alignments plus §5 and §6);
  `id 109` → `AmberHarbor` (CadQ's wiring status).
- Judgement rule that matters: `am mail send` returning an `id` proves nothing; the receipt tool's
  `found`/`NOT_FOUND` is the only delivery evidence, and a `--project` typo delivers silently into
  another project. Read an inbox with `am inbox --all` (a bare `am inbox` lists unread only).
- At the time of writing, the CadQ-side agent had **not** appeared in the roster, so the three-way
  discussion is still missing one corner.

## 8. Mailbox round 1: what the three planes agreed (2026-10-03)

Participants: `RoseElm` (onshapescript), `RoseStork` (MeshQ), `WindyIvy` (CadQ), coordinator
`AmberHarbor`. Message ids: 104/108/109 (opening), 112/113 (CadQ report + contact approval),
114 (MeshQ's answers), 116 (reply to CadQ), 117 (new measurements to MeshQ), 118 (reply to MeshQ).

### 8.1 Settled conventions (MeshQ proposed, this plane accepted)

- **A handoff has two blocks**: `declaration` (required — units, linear/angular tolerance, whether it
  is absolute, producer, export parameters) and `reference` (optional — per-solid volume/bbox/topology/
  cylindrical radii, explicitly labelled as *B-Rep-side readings*). Reason MeshQ gave: a print-fit
  verdict must be computable from **one mesh alone**, and the B-Rep numbers are then the truth to
  compare against, not an input.
- **Tolerance is declared by the receiver and acknowledged by the producer**, and the record must carry
  the acknowledgement, not just the value: `{linear_mm, angular_rad, absolute, declared_by, used_by, used}`.
  Two measured reasons: a unit declared wrong round-trips with 0.0 % error, and a relative vs absolute
  `0.05` tessellates 68 vs 144 faces (MeshQ ADR-0020).
- **Addressing is four fields, not one**: `(path, sha256, sha256_stable, geometry)`. A path is for
  people, a hash is download integrity, and when bytes are not stable the identity is the **geometry
  signature** (counts / volume / area / bbox in mm) — compared with MeshQ's one implementation
  (`meshq.geometry.same_geometry`). No plane should invent a geometry hash.
- **Print-fit: direction is a parameter of the question, not a property of the part.** MeshQ owns
  overhang/wall-thickness/topology *given a direction and a threshold*; it does not own the build
  envelope (the slicer does), and no conclusion is written back as a part-level fact.
- **Encapsulation**: the *surface* contract belongs in the shared `mcp_surface` library; the *artifact*
  contract must be **generated from each plane's runtime data**, never hand-copied (this plane already
  does that: `fdm_analysis/contracts.py` dataclasses → `as_dict()`). The library holds the schema id and
  the "refuse an unknown version" rule, with one pin. No router inside any of the three planes — a router
  would become a second copy of MeshQ's `ROUTE_ELSEWHERE` and the two would drift.
- **Cost metadata has two axes that must not be merged**: this plane's "where the work happens"
  (`offline|browser|live`, `estimated_requests`) and MeshQ's "what the tool does"
  (`report|artifacts|executes|control`).

### 8.2 Facts measured during the round that closed open questions

| Fact | Consequence |
|---|---|
| Real Onshape exports: 11 files, **2 of them hold 4 solids** (`gf-4u-bin-59f6cc99-1`, `gf-4u-bin-cn-a3cf38f6-1`), per-solid volumes identical | CadQ's `step_intake` finally has real multi-solid fixtures; handed over in message 116 |
| The same two files differ by **34 bytes** — only the STEP header's `/* name */` GUID and `/* time_stamp */` | a STEP sha256 is download integrity, **not** content identity; this plane will not claim `sha256_stable: true` for STEP |
| Boolean check on the 4-solid real export: 3 candidate pairs, **0 interfering, 3 touching, intersection volume exactly 0.000000 mm³** | a bounding-box-only check would have reported three clashes; the interlock case is not synthetic |
| This plane's configured angular tolerance default is **5.0°**, not MeshQ's declared 0.3 rad (≈17.19°) | "receiver declares, producer acknowledges" is not a formality here: the converter takes `--angular-tolerance-degrees` |
| This plane's L6 `report.json` already computes `watertight / bedContactAreaMm2 / printHeightMm / overhangAreaMm2 (@45°, downward-face-area)` with `wallThicknessMm: null` | the two planes both compute an "overhang area" under the same 45° threshold — ownership must be stated, or two planes will publish two numbers with one name |

### 8.3 What this plane owes, once the human agrees

1. Add a `geometry` block to the browser STEP manifest (reusing the existing AABB reading: solid count +
   per-solid bbox + volume + `measureKind: brep_exact`).
2. Add `absolute / declared_by / used_by / used` to the tessellation declaration and state the 0.05 mm /
   5.0° defaults explicitly.
3. Stop implying byte identity for STEP: `sha256_stable: false` plus the geometry signature.

### 8.4 CadQ's stated position (from its report, message 113)

CadQ can already **read** an external multi-solid STEP (commit `ef6bf69`; per-solid volume/bbox/topology/
cylindrical-face radii; fixture self-test relative differences ~1e-15; 10/10 suites, 494/494). Its
geometry-**modifying** half is deliberately not started: it waits for real parts, which §8.2 now supplies.
Its proposed division matches this plane's: parametric design → Onshape; exact B-Rep changes (split, hole
diameter and shrink compensation, split-and-dowel, screw bosses) → CadQ; mesh-level printability → MeshQ;
slicing and placement → the slicer; and **cross-plane traffic is files plus data, never imported code**.

## 9. What is deliberately not decided here

Which leg gets built first, where the shared contract page lives, and whether a fourth
consumer (the `modeling-token-bench` harness, which already re-verifies STEP with
OpenCascade and STL with the standard library) becomes a party to the same contract.
Those are the three-way discussion's calls, not this repo's.
