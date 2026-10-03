# Three-plane handoff manifest — schema draft v0.1

**Status: draft for field-level review.** This file is a *proposal* reviewed by the other two
planes over the `agent-infra` mailbox (messages 116/117/118 to `WindyIvy`/CadQ and
`RoseStork`/MeshQ). Nothing here is implemented behavior yet; per this repository's governance,
unimplemented ideas live in `roadmap/`. The capability matrix, the gaps and the boundary
positions are in `THREE_PLANE_GEOMETRY_INTEROP.md`; this file is only the artifact shape those
three planes would exchange.

## 1. What it is, and what it is not

- It is **one artifact description**, produced by whichever plane produced the artifact, consumed
  by whichever plane picks it up next.
- It is **not** a router: no plane dispatches to another plane through this file. Routing stays
  where it already is — MeshQ's named `ROUTE_ELSEWHERE` refusal, or an upper layer with its own
  owner (§6 of the interop page).
- It is **not** a second copy of any plane's internal manifest. Each plane generates its own
  fields from its own runtime data (this repository: `fdm_analysis/contracts.py` dataclasses →
  `as_dict()`), and maps them into this shape exactly once at the handoff boundary.

## 2. The shape

```jsonc
{
  "schema": "onshapescript.handoff/0.1-draft",   // namespaced id + version; an unknown version MUST be refused
  "produced_by": {"plane": "onshape|cadq|meshq", "identity": "<mailbox name>", "tool": "<tool>", "at": "<ISO8601>"},
  "source":      {"kind": "onshape_document|file", "reference": "<url or path>", "identifiers": {}},
  "units": "mm",                                  // always explicit; never inferred from a successful round trip
  "authority":   {"brep": "authoritative", "mesh": "derived", "statement": "<one sentence>"},

  "declaration": {                                // REQUIRED block
    "artifact":  {"role": "canonical|derived", "path": "", "media_type": "", "byte_count": 0},
    "identity":  {"sha256": "", "sha256_stable": true, "sha256_note": ""},
    "geometry":  {"measure_kind": "brep_exact|tessellation", "units": "mm", "solid_count": 0,
                  "parts": [{"index": 1, "name": "", "label": null, "bbox_mm": [0,0,0,0,0,0],
                             "volume_mm3": 0.0, "cross_plane_ref": "<export id>#<index>"}],
                  "producer_command": "<the exact command that measured this>",
                  "measured_tolerance_mm": 0.05},
    "tessellation": {"linear_tolerance_mm": 0.05, "angular_tolerance_rad": 0.0873, "absolute": true,
                     "declared_by": "<plane>", "used_by": "<plane>",
                     "used": {"linear_tolerance_mm": 0.05, "angular_tolerance_rad": 0.0873},
                     "kernel": "<kernel + version>"}
  },

  "reference": null,                              // OPTIONAL block: B-Rep readings kept as the truth to
                                                 // compare against, never as an input to a mesh verdict
  "cost": {"where": {"network": "offline|browser|live", "estimated_requests": 0, "mutating": false},
           "what":  {"kind": "report|artifacts|executes|control"}},
  "next_action": {"kind": "none|fix_backend|needs_human", "detail": ""}
}
```

Every field exists because one of the three planes already paid for its absence:

| Field | The measured failure it prevents |
|---|---|
| `schema` + version, refusal rule | A consumer cannot tell a compatible change from an incompatible one |
| `authority` statement | "Is this number the part, or one triangulation of it?" gets answered by prose in three repositories instead of by a field |
| `units` explicit | A wrong unit declaration round-trips with 0.0 % error (MeshQ's USD case: 40 mm declared as 40 m) |
| `identity.sha256_stable` + `geometry` | Measured here: two real Onshape exports of the same geometry differ by **34 bytes** (STEP header GUID + timestamp), so a hash alone is not an identity |
| `geometry.parts[].index` + `cross_plane_ref` | One Onshape export often holds several solids (2 of 11 real exports hold 4) |
| `tessellation.absolute` + `declared_by`/`used_by`/`used` | A relative and an absolute `0.05` tessellate 68 vs 144 faces; the receiver must declare and the producer must acknowledge what it actually used |
| `cost.where` × `cost.what` (two axes, not merged) | "Where the work happens" and "what the tool does" answer different questions; merging them makes one axis carry the other's meaning |
| `next_action` | A plane that cannot do something says where it belongs, instead of failing vaguely |

## 3. A real instance, generated from real records

This is not hand-written. It comes from the real 4-solid export
`gf-4u-bin-59f6cc99-1` plus a real measurement run, by this throwaway generator:

```python
src = json.loads((EXPORT / "step-manifest.json").read_text(encoding="utf-8"))     # real browser manifest
geo = json.loads(subprocess.run([PY, CONV, "--input", str(EXPORT / "model.step"),  # real measurement
                                 "--output", "-", "--mode", "aabb",
                                 "--linear-tolerance-mm", "0.05", "--parts", "",
                                 "--max-pairs", "4000"], capture_output=True, text=True, check=True).stdout)
```

```json
{
  "schema": "onshapescript.handoff/0.1-draft",
  "produced_by": {"plane": "onshape", "identity": "RoseElm", "tool": "browser_export_step",
                  "at": "2026-10-03T06:20:00Z"},
  "source": {
    "kind": "onshape_document",
    "reference": "https://cad.onshape.com/documents/1ef2be8f3d45e6f996af24ab/w/bac7c0bf31912a956c44d15a/e/59f6cc99890dd2fea26d5471",
    "identifiers": {"documentId": "1ef2be8f3d45e6f996af24ab",
                    "workspaceId": "bac7c0bf31912a956c44d15a",
                    "elementId": "59f6cc99890dd2fea26d5471"}
  },
  "units": "mm",
  "authority": {"brep": "authoritative", "mesh": "derived",
                "statement": "B-Rep is authoritative; a mesh is the result of one triangulation at a declared tolerance"},
  "declaration": {
    "artifact": {"role": "canonical", "path": "model.step", "media_type": "model/step", "byte_count": 85146},
    "identity": {"sha256": "b9ec383f722ebd812fc92fa5edb08ecb3987919033453a67ee2cd0518861c057",
                 "sha256_stable": false,
                 "sha256_note": "STEP carries a GUID and a timestamp in its header; the hash is download integrity, not content identity"},
    "geometry": {
      "measure_kind": "brep_exact", "units": "mm", "solid_count": 4,
      "parts": [
        {"index": 1, "name": "solid_01", "label": null, "bbox_mm": [-18.6, -18.6, 0.8, 18.6, 18.6, 2.6],
         "volume_mm3": 2486.956459, "cross_plane_ref": "gf-4u-bin-59f6cc99-1#1"},
        {"index": 2, "name": "solid_02", "label": null, "bbox_mm": [-20.75, -20.75, 2.6, 20.75, 20.75, 4.75],
         "volume_mm3": 3318.503987, "cross_plane_ref": "gf-4u-bin-59f6cc99-1#2"},
        {"index": 3, "name": "solid_03", "label": null, "bbox_mm": [-20.75, -20.75, 4.75, 20.75, 20.75, 32.4],
         "volume_mm3": 8017.823333, "cross_plane_ref": "gf-4u-bin-59f6cc99-1#3"},
        {"index": 4, "name": "solid_04", "label": null, "bbox_mm": [-18.6, -18.6, 0.0, 18.6, 18.6, 0.8],
         "volume_mm3": 1059.113156, "cross_plane_ref": "gf-4u-bin-59f6cc99-1#4"}
      ],
      "producer_command": "cadquery_interference.py --mode aabb --linear-tolerance-mm 0.05",
      "measured_tolerance_mm": 0.05
    }
  },
  "reference": null,
  "cost": {"where": {"network": "browser", "estimated_requests": 0, "mutating": true},
           "what": {"kind": "artifacts"}},
  "next_action": {"kind": "none", "detail": ""}
}
```

The same file's boolean reading (real, not a fixture) shows why `geometry` and not a hash carries
identity here: 4 solids, 3 candidate pairs, **0 interfering, 3 touching**, every intersection volume
exactly `0.000000 mm³`, box overlaps `[37.2, 37.2, 0.0]` and `[41.5, 41.5, 0.0]`. A bounding-box-only
check would report three clashes for a part that is merely assembled.

## 4. The tessellation declaration: what exists today, and the proposed extension

Recorded today (real geometry package manifest,
`onshape_browser_mode/outputs/geometry_packages/bench-bracket-phase1/manifest.json`):

```json
{"tessellation": {"linearToleranceMm": 0.05, "angularToleranceDegrees": 5.0}}
```

Proposed (names taken verbatim from MeshQ's answer, so that the same words mean the same thing in
both repositories):

```json
{"tessellation": {"linear_tolerance_mm": 0.05, "angular_tolerance_rad": 0.0873, "absolute": true,
                  "declared_by": "meshq", "used_by": "onshape",
                  "used": {"linear_tolerance_mm": 0.05, "angular_tolerance_rad": 0.0873},
                  "kernel": "cadquery-2.8.0+OCP-7.9.3.1"}}
```

Two things this makes visible that the current record hides: the value is **absolute** (the OCCT
linear deflection is a model-unit length, the angular one is radians), and **this plane's configured
default is 5.0°**, not MeshQ's declared 0.3 rad (≈17.19°). A handoff that does not say "receiver
declared X, producer used Y" cannot express that difference.

## 5. Refusal rules (a consumer must be able to say no)

1. Unknown `schema` id or a version it does not implement → refuse, name the version it saw.
2. `units` absent → refuse (never infer from a successful conversion).
3. `tessellation` present without `absolute` → refuse (a bare `0.05` is ambiguous by measurement).
4. A `geometry` block claiming `measure_kind: brep_exact` from a plane that only read a mesh, or
   `tessellation` for a verdict it did not compute → refuse.
5. `authority` absent when a downstream plane is asked to make a decision → refuse (the decision
   would silently pick a side).

## 6. Open naming question (the one place this draft is not aligned)

This repository's existing manifests are `camelCase` (`schemaVersion`, `byteCount`,
`linearToleranceMm`). MeshQ's proposed cross-plane names are `snake_case`. The draft above follows
MeshQ, because a cross-plane file is a new artifact and MeshQ's names were already agreed in round 1.
The alternative — keep `camelCase` everywhere and let consumers translate — is equally workable but
must be decided once: **one mapping, in one place, never two definitions of the same field.**
Objection window: field-level only.

## 7. What each plane still owes (unchanged by this draft)

- **Onshape (this plane)**: import capability (the structural gap), plus the three recording
  changes this draft implies — a `geometry` signature in the browser STEP manifest, the
  `absolute`/`declared_by`/`used_by`/`used` tessellation declaration, and no byte-identity claim for
  STEP (`sha256_stable: false` + geometry signature).
- **CadQ**: whether `step_intake` becomes an MCP tool, what per-solid key it wants to be referenced
  by across planes, and the three constraints for anything handed back to Onshape for import.
- **MeshQ**: whether a mesh-level verdict must be computable from the `declaration` block alone
  (this draft assumes yes), and which of the two `overhang` computations (this plane's L6 analyzer
  already computes one at 45°) remains the published one.

## 8. Evidence

| Claim | Evidence |
|---|---|
| 11 real Onshape exports, 2 hold 4 solids | `find /mnt/c/MCP/onshapescript/onshape_browser_mode/outputs/step_exports -name model.step` + per-file AABB reading |
| 34-byte difference between two exports of the same geometry | `cmp -l` → 34; `diff` → `/* name */` GUID + `/* time_stamp */` |
| Boolean reading of the real 4-solid export | `cadquery_interference.py --input … --output - --mode boolean --linear-tolerance-mm 0.05 --parts "" --max-pairs 4000` |
| Recorded tessellation defaults | `geometry_packages/bench-bracket-phase1/manifest.json` → `{"linearToleranceMm": 0.05, "angularToleranceDegrees": 5.0}` |
| Mailbox delivery | `tools/mail-delivery-receipt.sh --project /home/lijq/code/agent-infra --message-id <id>` → `found` |
