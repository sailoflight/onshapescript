# Three-plane handoff manifest — schema draft v0.4

**Status: v0.4, third review round folded in.** v0.1 was reviewed by `WindyIvy`/CadQ (message 123,
8 field comments) and `RoseStork`/MeshQ (messages 120/124/131/143/145). v0.2 folded those; v0.3 folds
MeshQ's 14-row second pass (message 131), the two direct conflicts it shares with CadQ, and the rules
that came out of the cross-plane overhang face-off (the evidence record is
`onshape_docs/verification/interop-overhang-faceoff-2026-10-03.md`). Every change is listed in §2b
(v0.1 → v0.2), §2c (v0.2 → v0.3) and §2d (v0.3 → v0.4) with the sender and the reason. Nothing here is implemented
behavior yet; per this repository's governance, unimplemented ideas live in `roadmap/`.

## 1. What it is, and what it is not

- It is **one artifact description**, produced by whichever plane produced the artifact, consumed
  by whichever plane picks it up next.
- It is **not** a router: no plane dispatches to another plane through this file. Routing stays
  where it already is — MeshQ's named `ROUTE_ELSEWHERE` refusal, or an upper layer with its own
  owner (§6 of the interop page).
- It is **not** a second copy of any plane's internal manifest. Each plane generates its own
  fields from its own runtime data (this repository: `fdm_analysis/contracts.py` dataclasses →
  `as_dict()`), and maps them into this shape exactly once at the handoff boundary.

- It is **not a verdict.** MeshQ measured this on its own side (message 120): it has no "printable"
  field at all — it computes geometry and answers *a caller-declared threshold*. This plane's numbers
  carry the same discipline: a measurement is not a decision, and the decision's threshold belongs to
  whoever asks.

## 2. The shape (v0.4)

```jsonc
{
  "schema": "onshapescript.handoff/0.4-draft",   // namespaced id + version; an unknown version MUST be refused
  "produced_by": {"plane": "onshape|cadq|meshq", "identity": "<mailbox name>", "tool": "<tool>",
                  "kind": "tool|script|human",    // a probe from a dev script is not a tool product
                  "at": "<ISO8601>"},
  // identifiers: a CLOSED key table per kind, so a missing one is refusable
  "source":      {"kind": "onshape_document|file", "reference": "<url or path>",
                  "identifiers": {"documentId": "", "workspaceId": "", "elementId": ""} },
  "units": "mm",                                  // THE only place the unit appears
  // APPLICABILITY: a field whose value is not physically meaningful in the state this manifest
  // reports must say so itself -- `{"applicable": false, "reason": ...}` -- rather than carry a
  // number the reader can only avoid by remembering a caveat. Measured basis: with an inverted
  // face present the signed volume is unchanged only when that face's plane contains the
  // integration reference point, and 21333.333333 (exactly wrong) when the same mesh is shifted
  // +Z 50 mm. So `volume_mm3`/`area_mm2` may only be read when `mesh_orientation.consistent` is
  // true, and `outwardOriented` is `applicable: false` whenever the winding is inconsistent --
  // one plane's own record contradicted itself on exactly this point (normals.consistent=false
  // while volume.outward_normals=true).

  "authority": {
    "artifact_is": "exact_geometry|triangulation_of_exact_geometry",   // what THIS artifact is
    "part_authoritative_in": "cadq|onshape|meshq",                     // who owns the exact reading
    // `order` hangs on the READINGS, not on the planes: it answers "when these two disagree, which do I
    // trust", which is decidable. A plane-level authority order would be a router, and no plane owns routing.
    "order": ["declaration.geometry", "reference.geometry"],
    "statement": "<one sentence, for a human>"
  },

  "declaration": {                                // REQUIRED block
    "artifact":  {"role": "canonical|derived", "path": "", "media_type": "", "byte_count": 0},
    "identity":  {"sha256": "", "sha256_stable": false,
                  "sha256_stable_evidence": null, // REQUIRED when stable is true: two digests of one input
                  "sha256_note": ""},             // REQUIRED when stable is false; geometry must be non-empty too
    "geometry":  {
      "measure": {"kind": "brep_exact|tessellation",   // a STRUCTURE, so the branch decides what must exist
                  "kernel": {"name": "occt|blender|...", "version": ""},
                  // `at` REQUIRED for tessellation and FORBIDDEN for brep_exact: a B-Rep reading has no
                  // tolerance, and the angular number binds as often as the linear one.
                  "at": {"linear_tolerance_mm": 0.05, "angular_tolerance_rad": 0.0873}},
      "solid_count": 0,
      "parts": [{"index": 1, "name": "", "label": null,
                 // named fields, not six loose numbers, and NOT the name a mesh kernel already uses
                 "bounds_mm": {"min": [0,0,0], "max": [0,0,0], "size": [0,0,0]},
                 "volume_mm3": 0.0,
                 "cross_plane_ref": {"export_id": "", "index": 1, "signature": "<optional digest, a label only>"},
                 // Any row that asks for a CHANGE must also carry a measurable selection rule: identity
                 // fields reference, they do not select, and a twin part has no distinguishing identity.
                 "selectors": []}],
      "identity_rule": {"sort_by": ["volume_mm3", "bounds_mm"], "compare": "relative",
                        "precision": 1e-6,            // the sort/match key
                        "equivalence_tolerance": 1e-6}, // "are these the same geometry" -- never left to each side
      "producer_command": "<the exact command that measured this>"
    },
    "mesh": null,                                 // REQUIRED for a mesh handoff, forbidden for exact geometry
    "tessellation": null                          // REQUIRED for a mesh handoff: see the shape below
  },

  "reference": null,                              // OPTIONAL: the other reading, kept to compare against,
                                                 // never an input to a mesh verdict
  "cost": {"where": {"network": "offline|browser|live", "mutating": false,
                     "estimated_requests": 0,    // FORBIDDEN when offline; REQUIRED when browser|live;
                                                 // null + reason when genuinely unknown (never 0 for "unknown")
                     "spent_quota": 0, "quota_remaining": null},
           "what":  {"kind": "report|artifacts|executes|control"}},
  "next_action": {"kind": "none|awaiting_peer|route_elsewhere|fix_backend|needs_human",
                  "route_to": {"plane": "meshq|cadq|onshape", "reason": ""},  // REQUIRED for route_elsewhere
                  "detail": ""}                   // must name a plane when kind is not none
}
```

### The mesh handoff block (the shape that a face-off proved necessary)

```jsonc
"declaration": {
  "mesh": {"role": "derived", "path": "", "media_type": "model/stl",
           "representation": "builder_polygons|stl_triangulation",  // a cube is 6 quads built, 12 triangles read back
           "triangle_count": 0},
  "tessellation": {
    "absolute": true,                              // relative and absolute 0.05 tessellate differently
    "declared_by": "<plane>", "used_by": "<plane>",
    "declared": {"linear_tolerance_mm": 0.05, "angular_tolerance_rad": 0.0873},
    "used": {"linear_tolerance_mm": 0.05, "angular_tolerance_rad": 0.0873},
    "matches_declaration": true,                   // producer-computed; FALSE without reporting is a refusal
    "deviation_reason": null,                      // REQUIRED when matches_declaration is false
    "read_back_from": "<the record the declaration was read from>", "read_back_at": "<ISO8601>",
    "kernel": {"name": "", "version": ""}
  },
  "mesh_orientation": {"consistent": true,         // a closed, consistently wound mesh meets every shared
                       "inconsistentEdgePairs": 0, // edge once per direction
                       "inconsistentFaceIndices": [],  // locatable: a bare count cannot be acted on
                       "outwardOriented": true,    // null when an open mesh cannot be judged ("not measured" != "outward")
                       "facesWithoutNormal": 0,    // a face with no usable normal is COUNTED, never dropped
                       "checkedEdges": 0}
}
```

Every field exists because one of the three planes already paid for its absence:

| Field | The measured failure it prevents |
|---|---|
| `schema` + version, refusal rule | A consumer cannot tell a compatible change from an incompatible one |
| `authority.order` (machine-checkable) + `statement` (human) | A one-sentence authority claim cannot be enforced by a program; CadQ asked for the order array for exactly that reason |
| `units` in **one** place | A wrong unit declaration round-trips with 0.0 % error (MeshQ's USD case: 40 mm declared as 40 m). Two copies of one value drift, so `geometry` carries no unit of its own |
| `identity.sha256_stable` (default false) + `sha256_stable_evidence` | Measured here: two real Onshape exports of the same geometry differ by **34 bytes** (STEP header GUID + timestamp). MeshQ's rule is default-untrusted: `true` requires evidence |
| `geometry.identity_rule` + `cross_plane_ref` | CadQ's real fixture `gf-storage-v25-U-two-legs.step` (70 solids) contains 8 identical `200×150×2` plates and 8 frames with 80 Ø7.8 holes: an index alone would silently rebind "change this one" to another part after a re-export reorders solids |
| `measure_kind` + `kernel`, and `measured_tolerance_mm` only for tessellation | B-Rep volume/bbox are analytic (CadQ measured 2.65e-15 relative error against hand-built values); stamping 0.05 mm on a truth hides the difference between truth and approximation |
| `tessellation.absolute` + `declared`/`used` + `matches_declaration` | A relative and an absolute `0.05` tessellate 68 vs 144 faces; and MeshQ's rule is *compute to the declared value*, so a silent tightening must be visible |
| `cost.where` × `cost.what` (two axes) + `spent_quota`/`quota_remaining` | "Where the work happens", "what the tool does" and "how much external resource it burned" are three different questions; only the producer knows the third |
| `next_action.kind: awaiting_peer` | In a real round trip the most common state is "the ball is with the other side"; calling that `none` says nobody owes anything |
| `next_action` at all | A plane that cannot do something says where it belongs, instead of failing vaguely |

## 2b. What changed from v0.1, who asked for it, and where the reviewers disagreed

| # | Change | Asked by | Resolution, and the reason it won |
|---|---|---|---|
| 1 | `cross_plane_ref` becomes `{export_id, index, signature}` and `geometry.identity_rule` is added | CadQ (msg 123 §1), MeshQ (msg 120 §2) | Both asked for cross-version identity. **MeshQ's comparison rule stays authoritative** (sorted multiset by volume then bbox, stated precision, relative 1e-6) and CadQ's digest is kept as an optional fast path — but computed over **full-precision** canonical values, not values rounded to 3 decimals: rounding blinds the digest to real differences *and* adds a rounding rule that would itself need versioning. A differing digest never proves two geometries differ; it sends you to the comparison rule |
| 2 | `measured_tolerance_mm` is `null` for `measure_kind: brep_exact` | CadQ (§2) | Analytic truth must not be labelled with an approximation tolerance |
| 3 | `units` at the top level only | CadQ (§3) vs MeshQ (§1) | **The one direct conflict.** MeshQ wanted a unit inside the measurement block ("a reader can see how the number was made"); CadQ wanted one place, and both sides state the same rule — one definition per field. Resolution: the unit stays at the top level; MeshQ's intent is served by `measure_kind` + `kernel` sitting next to the numbers, because *that* is what tells a reader how the numbers were made |
| 4 | `authority.order: ["brep","mesh"]` | CadQ (§4) | Free text cannot be judged by a program; the order array can |
| 5 | `cost.where.spent_quota` + optional `quota_remaining` | CadQ (§5) | Only the producer knows what it spent; CadQ is always 0 (local kernel), this plane is not |
| 6 | `next_action.kind += awaiting_peer` | CadQ (§6) | A real round trip spends most of its time there |
| 7 | `read_back_from` + `read_back_at` on the receipt | CadQ (§7) | MeshQ's gate reads the declaration back from a record; without naming that record, "the tolerance was read" is unprovable |
| 8 | `matches_declaration` + the rule *compute to the declared value* | MeshQ (§ tolerance) | This plane's configured default (5.0°) is **finer** than MeshQ's declared 0.3 rad (≈17.19°), so a silent difference is a real possibility, not a hypothetical |
| 9 | `kernel` beside `measure_kind` | MeshQ (§1) | One glance tells the next reader how a number was produced |
| 10 | Cross-plane `snake_case`, one mapping at the boundary | CadQ (§8), MeshQ (consistent) | CadQ's own identifiers are already snake_case, so it needs no mapping; "translate at every consumer" would produce two translators for one field. §6 is thereby closed |
| 11 | `sha256_stable` defaults to false; `true` requires two digests | MeshQ (§ sha256) | Default-untrusted is the only rule that survives a format list where FBX and ABC change on every export |

## 2c. What changed from v0.2 to v0.3, and why

| # | Change | Asked by | Resolution |
|---|---|---|---|
| 1 | `measure_kind` becomes `geometry.measure = {kind, kernel{name,version}, at{linear,angular}}`; `measured_tolerance_mm` and `measured_at` are gone | MeshQ (131 rows 1/2/12), CadQ (123 §1/§2) | Both reviewers asked for a structure rather than a scalar. `at` is required for `tessellation` and forbidden for `brep_exact`. MeshQ's measured reason: the **angular** number is the one that binds (0.3 rad → 184 faces while the linear tolerance from 0.05 to 2.0 mm changes nothing), so a single scalar would report "tolerance unchanged" for a real change |
| 2 | `parts[].bbox_mm` (six loose numbers) becomes `parts[].bounds_mm{min,max,size}` | MeshQ (131 row 3) | Six numbers force the reader to guess the order, and MeshQ already uses `bounds_mm` for this triple — the same name for two meanings is exactly what this draft exists to prevent |
| 3 | `parts[].selectors` added, and a change request must carry one | MeshQ (131 row 4) | Identity references, it does not select: eight identical plates share a signature, so "change this one" must be expressed as a measurable rule (dimensions, cylinder radius, bounds, count) |
| 4 | `identity_rule.equivalence_tolerance` added beside `precision` | MeshQ (143) | "Sort/match key" and "are these the same geometry" are two questions; without a declared value each side picks its own |
| 5 | `sha256_stable: false` requires `sha256_note` **and** a non-empty `geometry`; `true` requires evidence | MeshQ (131 row 6) | Default-untrusted is the safe direction, and an unstable digest must have a replacement identity or the manifest names an artifact nobody can reference |
| 6 | `authority` gains `artifact_is` + `part_authoritative_in`, and `order` points at **readings** | MeshQ (131 row 8, 145 §4), CadQ (123 §4) | **The second direct conflict, resolved.** CadQ wants a machine-checkable order (free text cannot be judged); MeshQ wants the assertion to be about *this artifact*, because plane-level authority would make the manifest a router. Both hold: `artifact_is` says what this is, `order` says which reading wins on a conflict. `["declaration.geometry", "reference.geometry"]` is decidable and routes nothing |
| 7 | `cost.where.estimated_requests`: forbidden offline, required online, `null` + reason when unknown | MeshQ (131 row 9) | `0` carries two meanings ("no requests" vs "not known"); this repository's own rule is that an unmeasured number is not zero |
| 8 | `next_action` gains `route_elsewhere` + `route_to{plane,reason}` | MeshQ (131 row 10) | MeshQ's `FormatUnsupported` names who should take over; a refusal that names no destination is where "who owns this" starts being argued again |
| 9 | `source.identifiers` becomes a closed key table per `kind` | MeshQ (131 row 11) | An open dictionary cannot be validated; a closed table makes a missing key refusable |
| 10 | `tessellation.used` gains `deviation_reason`; `matches_declaration` is producer-computed | MeshQ (131 rows 13, 120) | "Compute to the declared value" is the whole point of the declaration; a silent tightening makes the declaration decorative |
| 11 | `produced_by.kind: tool|script|human` | MeshQ (145 §5) | A probe from a dev script is not a tool product, and the *reader* should not have to remember which is which |
| 12 | The mesh block carries `representation` plus `mesh_orientation` | MeshQ (131 row 7, 145 §3) + the face-off | A cube is 6 quads when built and 12 triangles when read back from STL, so a bare face count is not comparable; and a face-off here proved that a **watertight** mesh can still carry an inverted face whose reading is silently wrong, so a mesh handoff must state whether the winding was checked |
| 13 | `bed_contact_area` is one policy read at two thresholds, not a second printability number | MeshQ (143) | The same `downward-face-area` policy at threshold → 0 reproduced it to 2.0e-8, i.e. they are the same measurement, not two numbers that can disagree |
| 14 | Rules for any boundary test piece | MeshQ (145 §1) | Both implementations are correct and land on **opposite** sides when a face normal sits exactly on the threshold (their `worst_tilt_deg = 45.000001` → 0.0, my computed `normal_z` → 440.0). Boundary pieces must use 44.95/45.05, and the manifest must state that the decision is a computed float comparison — a **convention**, not an error |
| 15 | Compare bytes first | MeshQ (143) | "Declarations govern trust, bytes govern comparability": two sides tessellating the same part with different tolerances are not comparing the same thing |

## 2d. What changed from v0.3 to v0.4, and why

| # | Change | Asked by | Resolution |
|---|---|---|---|
| 16 | Every measured quantity gains an `applicable` flag, and the orientation-gated ones may not be read without it | MeshQ (151 §C, §D) | MeshQ's answer to "volume is blind to an inverted face" was not a disclaimer but a field that turns itself off: with an inverted face, `volume.applicable = false`. That is stronger than a note because a reader who never sees the number cannot read it wrongly. This draft adopts it as a general rule and names the gate explicitly |
| 17 | The blindness rule is stated in its conditional form | MeshQ (151 §C) | My claim was "the volume is blind to a single inverted face"; MeshQ measured that it is blind **iff that face's plane contains the integration reference point** (clean cube 8000.0 → flipped bottom face at z=0: 8000.0 again → the same mesh shifted +Z 50: **21333.333333**, matching `8000 − 2·c_f` with `c_f = (1/3)(−50)(400)` exactly). So "the volume is unreliable" was too broad and "the volume is fine" would have been wrong: **the observability of a defect depends on where the part sits**, and orientation state must never be inferred from a volume |

## 3. A real instance, generated from real records (regenerated for every version)

This is not hand-written. It comes from the real 4-solid export
`gf-4u-bin-59f6cc99-1` plus a real measurement run, by this throwaway generator:

```python
src = json.loads((EXPORT / "step-manifest.json").read_text(encoding="utf-8"))     # real browser manifest
geo = json.loads(subprocess.run([PY, CONV, "--input", str(EXPORT / "model.step"),  # real measurement
                                 "--output", "-", "--mode", "aabb",
                                 "--linear-tolerance-mm", "0.05", "--parts", "",
                                 "--max-pairs", "4000"], capture_output=True, text=True, check=True).stdout)
# the identity both reviewers asked for, over full precision (no rounding before hashing):
canonical = json.dumps(sorted(([[repr(v) for v in p["bbox_mm"]], repr(p["volume_mm3"])] for p in geo["parts"]),
                              key=lambda item: (float(item[1]), item[0])), separators=(",", ":"))
signature = hashlib.sha256(canonical.encode("utf-8")).hexdigest()                  # 6ba0265e063c…
```

```json
{
  "schema": "onshapescript.handoff/0.4-draft",
  "produced_by": {
    "plane": "onshape",
    "identity": "RoseElm",
    "tool": "browser_export_step",
    "kind": "tool",
    "at": "2026-10-03T06:20:00Z"
  },
  "source": {
    "kind": "onshape_document",
    "reference": "https://cad.onshape.com/documents/1ef2be8f3d45e6f996af24ab/w/bac7c0bf31912a956c44d15a/e/59f6cc99890dd2fea26d5471",
    "identifiers": {
      "documentId": "1ef2be8f3d45e6f996af24ab",
      "workspaceId": "bac7c0bf31912a956c44d15a",
      "elementId": "59f6cc99890dd2fea26d5471"
    }
  },
  "units": "mm",
  "authority": {
    "artifact_is": "exact_geometry",
    "part_authoritative_in": "onshape",
    "order": [
      "declaration.geometry",
      "reference.geometry"
    ],
    "statement": "B-Rep is authoritative; a mesh is the result of one triangulation at a declared tolerance"
  },
  "declaration": {
    "artifact": {
      "role": "canonical",
      "path": "model.step",
      "media_type": "model/step",
      "byte_count": 85146
    },
    "identity": {
      "sha256": "b9ec383f722ebd812fc92fa5edb08ecb3987919033453a67ee2cd0518861c057",
      "sha256_stable": false,
      "sha256_stable_evidence": null,
      "sha256_note": "STEP carries a GUID and a timestamp in its header; the digest is download integrity, not content identity"
    },
    "geometry": {
      "measure": {
        "kind": "brep_exact",
        "kernel": {
          "name": "occt",
          "version": "7.9.3.1"
        },
        "at": null
      },
      "solid_count": 4,
      "parts": [
        {
          "index": 1,
          "name": "solid_01",
          "label": null,
          "bounds_mm": {
            "min": [
              -18.6,
              -18.6,
              0.8
            ],
            "max": [
              18.6,
              18.6,
              2.6
            ],
            "size": [
              37.2,
              37.2,
              1.8
            ]
          },
          "volume_mm3": 2486.956459,
          "cross_plane_ref": {
            "export_id": "gf-4u-bin-59f6cc99-1",
            "index": 1,
            "signature": "6ba0265e063c"
          }
        },
        {
          "index": 2,
          "name": "solid_02",
          "label": null,
          "bounds_mm": {
            "min": [
              -20.75,
              -20.75,
              2.6
            ],
            "max": [
              20.75,
              20.75,
              4.75
            ],
            "size": [
              41.5,
              41.5,
              2.15
            ]
          },
          "volume_mm3": 3318.503987,
          "cross_plane_ref": {
            "export_id": "gf-4u-bin-59f6cc99-1",
            "index": 2,
            "signature": "6ba0265e063c"
          }
        },
        {
          "index": 3,
          "name": "solid_03",
          "label": null,
          "bounds_mm": {
            "min": [
              -20.75,
              -20.75,
              4.75
            ],
            "max": [
              20.75,
              20.75,
              32.4
            ],
            "size": [
              41.5,
              41.5,
              27.65
            ]
          },
          "volume_mm3": 8017.823333,
          "cross_plane_ref": {
            "export_id": "gf-4u-bin-59f6cc99-1",
            "index": 3,
            "signature": "6ba0265e063c"
          }
        },
        {
          "index": 4,
          "name": "solid_04",
          "label": null,
          "bounds_mm": {
            "min": [
              -18.6,
              -18.6,
              -0.0
            ],
            "max": [
              18.6,
              18.6,
              0.8
            ],
            "size": [
              37.2,
              37.2,
              0.8
            ]
          },
          "volume_mm3": 1059.113156,
          "cross_plane_ref": {
            "export_id": "gf-4u-bin-59f6cc99-1",
            "index": 4,
            "signature": "6ba0265e063c"
          }
        }
      ],
      "identity_rule": {
        "sort_by": [
          "volume_mm3",
          "bounds_mm"
        ],
        "compare": "relative",
        "precision": 1e-06,
        "equivalence_tolerance": 1e-06,
        "set_signature_sha256": "6ba0265e063c75413b41ec0df7871c6b0c4a176d1d9cf201364357f309dcc83a",
        "note": "the digest is a fast path; if two digests differ, compare with the rule above instead of concluding"
      },
      "producer_command": "cadquery_interference.py --mode aabb --linear-tolerance-mm 0.05"
    }
  },
  "reference": null,
  "cost": {
    "where": {
      "network": "browser",
      "estimated_requests": 0,
      "mutating": true,
      "spent_quota": 0,
      "quota_remaining": 2380
    },
    "what": {
      "kind": "artifacts"
    }
  },
  "next_action": {
    "kind": "awaiting_peer",
    "detail": "CadQ/MeshQ field review of v0.2"
  }
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
6. The unit present in more than one place → refuse (one definition per field; two copies drift).
7. A geometry digest that differs used *as* proof of different geometry → refuse: digests are a fast
   path, and only `identity_rule` decides.
8. `measured_tolerance_mm` non-null with `measure_kind: brep_exact` → refuse: analytic truth is not an
   approximation.
9. `tessellation.matches_declaration: false` without the mismatch being reported to the caller →
   refuse: the declaration must not be quietly adjusted.

10. `identity.sha256_stable == false` **and** `geometry` empty → refuse (no identity and no replacement).
11. `measure.kind == "tessellation"` **without** the `at` pair, or `measure.kind == "brep_exact"` **with**
    it → refuse (the branch decides which fields may exist).
12. A mesh handoff without `tessellation.used` → refuse (a declaration with no receipt).
13. `tessellation.absolute`, `declared_by` or `used_by` missing on a mesh handoff → refuse ("who declared
    this" must be answerable).
15. A calibrated quantity (`volume_mm3`, `area_mm2`, `outwardOriented`) read while
    `mesh_orientation.consistent` is false, or without its `applicable` flag → refuse: the value is not
    physically meaningful in that state, and "the reader will remember the caveat" is not a mechanism.
16. A mesh handoff whose `mesh_orientation` is absent → refuse: a watertight mesh can still carry an
    inverted face whose reading is silently wrong, so "was the winding checked" is part of the artifact.

Rule 5 ("asked to make a decision") is a rule for the **caller**, not a manifest check: the manifest
cannot know what a consumer is about to do with it. Stated here so nobody implements a validator for a
condition it cannot observe.

## 6. Naming and key-set conformance: closed in v0.4

This repository's existing manifests are `camelCase` (`schemaVersion`, `byteCount`,
`linearToleranceMm`) while the cross-plane names are `snake_case`. Both reviewers supported the same
resolution: **the cross-plane file is snake_case, with exactly one mapping at the handoff boundary.**
CadQ's internal identifiers are already snake_case, so it needs no mapping; the alternative ("keep
camelCase and let every consumer translate") would produce two translators for one field, which is the
failure this rule exists to prevent. The mapping lives in this repository, once, next to whatever
produces the file.

MeshQ added the criterion that keeps that rule honest: **the cross-plane key set must equal the schema's
required set — one extra or one missing key is red.** A convention nobody checks is prose, and the
failure mode of this repository family is "if it can be generated, do not hand-write it; the handwritten
copy drifts".

## 7. What each plane still owes (as of v0.4)

- **Onshape (this plane)**: import capability (the structural gap, now planned at
  `onshape_rest_api_mode/step_import.py` and blocked on a multipart transport — see the interop
  page §9), plus the three recording changes this draft implies — a `geometry` block in the browser
  STEP manifest, the tessellation declaration with `absolute`/`declared`/`used`/`matches_declaration`,
  and no byte-identity claim for STEP (`sha256_stable: false` plus the geometry identity rule).
- **CadQ**: answered in message 123 — `step_intake` becoming an MCP tool is its lead's public-contract
  decision (registered as open item 11, not answered by the agent), the read side is settled at
  `cad_agent/core/step_intake.py:parts_of_step()` (`index / label / valid / solid / volume / area /
  bbox{min,max,size} / center_of_mass / topology{faces,edges,vertices} / cylindrical_faces /
  planar_faces`, read-only, no confirmation gate; only *writes* take dry-run + confirm), and its three
  hand-back constraints (pending its lead) are: do not overwrite `model.step` — land a changed part in a
  neutral drop directory as `<export_id>__print.step` with path + sha256 + geometry signature in the
  message; units always `mm` + AP242; a STEP handoff carries **no** tessellation tolerance, and only a
  mesh handoff carries `absolute: true` + `declared_by/used_by/used`. CadQ's first real load is
  `gf-storage-v25-U-two-legs.step` (70 solids, 407.9×380×230 mm), whose changes *will* alter part
  signatures — it will report field-level errors against this draft when it writes that record.
- **MeshQ**: answered in message 120 — it accepts the `geometry` block (after reading this plane's
  converter source, so `brep_exact` is verified rather than asserted), requires `kernel`, holds that
  `index` is display order and not identity, holds that a bounding-box overlap is a candidate and never
  a verdict, and states it has **no** "printable" field at all: it computes geometry plus the truth of a
  *caller-declared* threshold, and never stamps a verdict onto anyone's artifact.

## 8. Evidence

| Claim | Evidence |
|---|---|
| 11 real Onshape exports, 2 hold 4 solids | `find /mnt/c/MCP/onshapescript/onshape_browser_mode/outputs/step_exports -name model.step` + per-file AABB reading |
| 34-byte difference between two exports of the same geometry | `cmp -l` → 34; `diff` → `/* name */` GUID + `/* time_stamp */` |
| Boolean reading of the real 4-solid export | `cadquery_interference.py --input … --output - --mode boolean --linear-tolerance-mm 0.05 --parts "" --max-pairs 4000` |
| Recorded tessellation defaults | `geometry_packages/bench-bracket-phase1/manifest.json` → `{"linearToleranceMm": 0.05, "angularToleranceDegrees": 5.0}` |
| Mailbox delivery | `tools/mail-delivery-receipt.sh --project /home/lijq/code/agent-infra --message-id <id>` → `found` |
| The v0.2 instance is generated, not written | `/tmp/draft_handoff_instance_v02.py` reads the real `step-manifest.json`, runs the real measurement, and emits the block above; the set signature is `6ba0265e063c7541…` |
| Peer review of v0.1 | mailbox messages 120 (MeshQ) and 123 (CadQ), each ack'd against the id; `mail-delivery-receipt.sh` reported `found` for the outbound 116/117/118/119 |
| Volume blindness is conditional, measured by the other plane | MeshQ message 151 §C: clean cube 8000.0; flipped bottom face in the z=0 plane 8000.0 (unchanged); the same mesh at +Z 50 mm 21333.333333, matching the closed form `8000 − 2·c_f` exactly |
| Overhang face-off, both directions | `onshape_docs/verification/interop-overhang-faceoff-2026-10-03.md` (relative differences 1.77e-8 / 2.0e-8 / 3.5e-9; both sides low by 4.9e-5 against the sphere's closed form), including the retraction of my own first probe set |
| Import request shape | vendored OpenAPI `createTranslation` + `BTBTranslationRequestParams`; `dev/tests/test_rest_step_import.py` cross-checks every sent and unsent field against that schema |
