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

## 5. What is deliberately not decided here

Which leg gets built first, where the shared contract page lives, and whether a fourth
consumer (the `modeling-token-bench` harness, which already re-verifies STEP with
OpenCascade and STL with the standard library) becomes a party to the same contract.
Those are the three-way discussion's calls, not this repo's.
