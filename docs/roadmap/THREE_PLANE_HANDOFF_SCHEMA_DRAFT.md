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
| `geometry.measure{kind, kernel{name,version}, at}` with `at` only for `tessellation` | B-Rep volume/bbox are analytic (CadQ measured 2.65e-15 relative error against hand-built values); stamping 0.05 mm on a truth hides the difference between truth and approximation. The branch decides which fields may exist, so a validator cannot look for a tolerance on an exact reading |
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
| 16 | Every measured quantity gains an `applicable` flag, and the **winding-dependent** ones may not be read without it | MeshQ (151 §C/§D, corrected in 163 §B) | MeshQ's answer to "volume is blind to an inverted face" was not a disclaimer but a field that turns itself off: with an inverted face, `volume.applicable = false`. Adopted as a general rule — **but the first version of it named `area_mm2`, and that was wrong**: area is `Σ|Aᵢ|`, independent of winding, so gating it would refuse a usable number (MeshQ measured 2400.0 on three variants) while the genuinely dependent class — everything derived from face normals, including `overhang` — was missing. The rule is therefore stated by nature with two example lists (§5 rule 15). The correction is kept visible here rather than edited away: a rule that asserted the opposite of the measurement is worse than no rule |
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
        "note": "digests are a fast path in BOTH directions: a differing digest is not proof of different geometry, and an equal digest is not proof of identical geometry; only this rule + equivalence_tolerance decide"
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

### Why `matches_declaration` is not the same as "good enough" (CadQ's measurement, message 156)

A declaration can be honoured exactly and still miss the consumer's gate. On a real piece from the
70-solid fixture (exact volume 324.5878 mm³), CadQ measured the mesh's volume error against the exact
value:

| declared / used | volume error | MeshQ's volume gate (0.05 %) |
|---|---|---|
| 0.05 mm / **0.3 rad** | 0.103 % | **fails** (12 of the 70 pieces exceed it) |
| 0.05 mm / **0.1 rad** | 0.012 % | passes |
| **0.02 mm** / 0.1 rad | **bit-identical to the 0.05 mm row** | — |

Two consequences the schema has to carry, and both are now in the shape above:

1. `matches_declaration: true` means "the producer used what was declared", **not** "the result meets the
   consumer's requirement". A consumer still needs its own acceptance gate, and the producer must not be
   asked to certify a gate it does not own.
2. **The angular tolerance is the binding one.** Tightening the linear tolerance from 0.05 to 0.02 mm
   changed nothing at all, while the angular one moved the error by a factor of ~8.6. A single scalar
   "tolerance" field would have reported "unchanged" for the real change and "changed" for the change
   that did nothing — this is the measured reason `measure.at` carries both components.
3. This run declares 0.1 rad for exactly this reason: 0.3 rad would have been honest (declared = used)
   and would have failed MeshQ's gate anyway.

### One field name may not carry numbers computed by different methods

`bounds_mm` had exactly that problem, and four readers produced **four** answers for one piece (MeshQ 170
§3: max gap **3.19e-2 mm**, on 70/70 pieces):

| Family | How it is read | Piece #0 `max` | Piece #2 `max` |
|---|---|---|---|
| Mesh vertices | the artifact's own bytes | `[7.0, 380.0, 86.0]` | `[220.699997, 348.0, 185.350006]` |
| Exact B-Rep, read **before** tessellation | `Bnd_Box` over the exact geometry | `[7.0, 380.0000001, 86.0]` | `[220.7, 348.0, 185.35]` |
| Exact B-Rep, read **after** exporting the STL | the same call, over a mutated cache | `[7.0000001, 380.0008704, 86.0000001]` | `[220.700488, 348.0000001, 185.381891]` |
| MeshQ's own reader | its kernel over the same bytes | `[7.0, 380.0, 86.0]` | `[220.699997, 348.0, 185.350006]` |

Measured root cause of the third row, and it is a real trap: **CadQuery's STL export mutates the shape's
cached bounds.** Same shape, same process, before → after `cq.exporters.export(..., 'STL')`:
`ymax 380.0000001000 → 380.0008703904` (#0) and `xmin 7.5000000000 → 7.4995117079` (#2). Reading the box
after the export is how this repository published a number in no other implementation's family while its
own self-comparison happily reported "no gap". Consequences now in the shape:

* `bounds_mm` is the **mesh-vertex** family and declares it (`boundsAlgorithm`), because that is the one
  any consumer can reproduce from the artifact bytes;
* the exact box travels beside it with its own algorithm, and the post-export box is kept as
  `boundsAfterTessellationMm` + `boundsMutatedByExport` (true on 70/70 pieces) so the mutation is visible
  rather than hidden;
* the mesh-vs-exact difference is a **method gap** (`boundsMethodGapMm`, up to the declared deflection,
  because a chord lies inside the surface it approximates), while the same-family cross-run difference is
  a **separate field** (`boundsCrossRunMm`, measured 0.0 on all 70 pieces) — only the second can find a
  tessellation that did not reproduce, and comparing across families is a false-alarm generator;
* the identity rule's tolerance is **per quantity** (`{volume: 1e-6, bounds: 1e-3}` with declared
  quanta), because one number cannot govern a quantity that agrees to 1e-9 and one that differs by 3e-2
  between families and by ~3e-6 between two implementations of the same family. Rounding does not remove
  the risk of a straddled bin; it is declared, and the digest stays a convenience rather than a proof.

### A cross-plane agreement must report the per-piece maximum and the worst piece

MeshQ's upgrade of this repository's own note, and its own mistake: in one batch the **aggregate**
relative difference was 1.31e-7 while the **per-piece maximum** was 3.39e-6 — a factor of 26, hidden by
reporting the aggregate alone (cancellation flatters a sum). A cross-plane consistency claim therefore
reports the per-piece maximum **and the worst piece's index**, never only the total.

### The kernel string is canonicalized, and a binding claim carries its factor

* `kernel.version` had two spellings for one kernel (`2.8.0+7.9.3.1` here, `2.8.0+OCCT-7.9.3.1` at CadQ),
  and "can these two even be compared" hangs on the kernel identity: the convention is now
  `<cadquery-version>+OCCT-<occt-version>`, published as `version_convention`.
* "Linear does not bind" is only true **relative to a tightening factor**: 2.5× (0.05 → 0.02 mm) leaves
  the triangle counts bit-identical, while 32× (0.05 → 0.0016 mm) does change them (CadQ 169 §1), so the
  claim must name the factor it was measured at.

### A "which tolerance binds" claim must be derived, never asserted

CadQ's manifest carried `binding: {linear: true, angular: null}` while its own measurement said the
opposite, and MeshQ caught it as the first thing to change: linear 0.05 → 0.02 → 0.01 left the triangle
counts **bit-identical** (376 / 1044), while 0.3 rad vs 0.1 rad changed **31 of 70** pieces' bytes
(39 identical). So the true value is `{linear: false, angular: true}`. A field that states the reverse of
the measurement is worse than an absent field, because a reader believes it. Contract consequence: if a
producer wants to publish which tolerance binds, it must **publish the measurement that decides it**
(the two triangle counts, or the two byte-digest sets); otherwise the field may not be published at all.

## 5. Refusal rules (a consumer must be able to say no)

1. Unknown `schema` id or a version it does not implement → refuse, name the version it saw.
2. `units` absent → refuse (never infer from a successful conversion).
3. `tessellation` present without `absolute` → refuse (a bare `0.05` is ambiguous by measurement).
4. A `geometry` block whose `measure.kind` claims more than was actually read — `brep_exact` from a plane
   that only read a mesh, or `tessellation` for a verdict it did not compute → refuse.
5. `authority` absent when a downstream plane is asked to make a decision → refuse (the decision
   would silently pick a side).
6. The unit present in more than one place → refuse (one definition per field; two copies drift).
7. A geometry digest used in **either** direction as a verdict → refuse: a differing digest is not
   proof of different geometry, and an equal digest is not proof of identical geometry (two
   implementations or two triangulations of one part can hash differently). Digests are a fast path;
   only `identity_rule` + `equivalence_tolerance` decide.
8. `solid_count` disagreeing with the number of `parts` rows, or two rows sharing an `index` → refuse:
   the two counts state the same fact twice, and a reader that trusts the wrong one miscounts a document
   (the real 70-solid fixture has 8-way identical groups, so a wrong count is not self-correcting).
9. `tessellation.matches_declaration: false` without the mismatch being reported to the caller →
   refuse: the declaration must not be quietly adjusted.

10. `identity.sha256_stable == false` **and** `geometry` empty → refuse (no identity and no replacement).
11. `measure.kind == "tessellation"` **without** the `at` pair, or `measure.kind == "brep_exact"` **with**
    it → refuse (the branch decides which fields may exist).
12. A mesh handoff without `tessellation.used` → refuse (a declaration with no receipt).
13. `tessellation.absolute`, `declared_by` or `used_by` missing on a mesh handoff → refuse ("who declared
    this" must be answerable).
14. A mesh handoff whose `mesh_orientation` is absent → refuse: a watertight mesh can still carry an
    inverted face whose reading is silently wrong, so "was the winding checked" is part of the artifact.
15. A reading that **depends on the winding** read while `mesh_orientation.consistent` is false — or
    without its `applicable` flag — → refuse. This rule is written **by nature, not by field name**,
    because the first draft of it named `area_mm2` and was wrong (MeshQ disproved it with three
    variants). The two classes, each with the measurement that settles it:

    * **winding-dependent → must go `applicable: false`**: signed / divergence volume,
      `outwardOriented`, and **every direction-derived reading** — `overhang` area, counted overhang
      faces, `worst_tilt_deg`. Measured here: flipping one slope's winding moved the counted overhang
      area from **0.0 to 565.192416792** (the retracted ramp; the retraction and its replacement
      fixture are recorded in `onshape_docs/verification/interop-overhang-faceoff-2026-10-03.md`), i.e.
      the reading is a function of
      the normals.
    * **winding-independent → must STAY readable**: `area_mm2` (it is `Σ|Aᵢ|`, so the winding never
      enters), face / triangle / vertex counts, and `bounds_mm`. MeshQ measured `surface_area_mm2 =
      2400.0` on all three variants, including the one shifted `+Z 50` where the volume is wrong by
      13333.33 mm³.

    A field that needlessly turns itself off costs the reader a number it could have used; a field that
    should have turned itself off and did not costs the reader a wrong one. Both are defects.
16. A winding verdict (`mesh_orientation.consistent`) read without regard to whether the edge graph is
    closed → refuse. **A consistent winding over a broken edge graph is VACUOUSLY consistent**: every
    surviving shared edge can be used once in each direction while the mesh is open, non-manifold or
    degenerate, so `consistent: true` there is not a verified winding. Measured while building the
    flipped-piece probe (this repository, 2026-10-03): a degenerate triangle (two identical vertices,
    from getting the binary-STL vertex offsets wrong) gave `watertight: false`, `nonManifoldEdges: 1`
    **and `consistent: true`** — over a shredded edge graph, where the check proves nothing. A producer
    must publish `applicable` beside `consistent` (with the reason), and a consumer must not read one
    without the other. Same class as rule 15, and it arrived the same way: not from reasoning but from a
    measurement that contradicted an assumption.

Rule 5 ("asked to make a decision") is a rule for the **caller**, not a manifest check: the manifest
cannot know what a consumer is about to do with it. Stated here so nobody implements a validator for a
condition it cannot observe.
17. A field that disagrees with the delivered artifact's own bytes → refuse the field, not the artifact.
    **The bytes are the referee**, because they are the one thing every plane holds identically: measured
    in the 70-piece join, two producers' STL files are byte-identical piece for piece, so a bounding-box
    field that differs from those bytes cannot describe them (CadQ's `tessellation.bounds_mm` carries the
    exact value `399.9` where its own bytes read `399.8999938964844` — a 1.2207e-05 mm gap on 67/70 pieces,
    while this repository's mesh field matches the bytes on 70/70). A reader that trusts the field over the
    bytes sees a geometry difference that does not exist, and the reverse ordering would have blamed the
    artifact.
18. A rule set that only says what to do when a field is PRESENT → refuse the rule set. **An absent or
    null field must be as loud as a field that says no**, because "undeclared" is not "fine" — and it is
    more dangerous than an explicit no, since nobody reads a field that is not there. Measured, not
    theorised: ten adversarial variants were run against this repository's print-basis guard and **six were
    blocked while four passed silently**, all four of the same family — the whole `orientation` block
    deleted, `applicable` set to null, an `unknown` thickness grade with no reason, and two null reference
    points. Every rule in the guard had been written as "what to do when the field says X"; deleting the
    field deleted the rule. So a required field is *required* (a missing one is a refusal, not a default),
    `null` is distinguished from absent, and the checker is tested with the field **deleted**.

## 6. Naming and key-set conformance: closed in v0.4

This repository's existing manifests are `camelCase` (`schemaVersion`, `byteCount`,
`linearToleranceMm`) while the cross-plane names are `snake_case`. Both reviewers supported the same
resolution: **the cross-plane file is snake_case, with exactly one mapping at the handoff boundary.**
CadQ's internal identifiers are already snake_case, so it needs no mapping; the alternative ("keep
camelCase and let every consumer translate") would produce two translators for one field, which is the
failure this rule exists to prevent. The mapping lives in this repository, once, next to whatever
produces the file.

MeshQ added the criterion that keeps that rule honest: **the cross-plane key set must equal the schema's
required set — one extra or one missing key is red.** The same measure applies to this draft's own
refusal-rule table: it must be **derived from §2's schema**, not hand-written. MeshQ caught exactly that
drift by reading the text (`8d33e76`): rules 4 and 8 still named `measure_kind` / `measured_tolerance_mm`
after v0.3 had deleted those keys, and rule 8 had become a duplicate of rule 11 — so a consumer
implementing §5 would have looked for keys that no longer exist. Historical change tables (§2b-§2d) keep
the old names on purpose; only the current-text tables are generated from the schema. A convention nobody checks is prose, and the
failure mode of this repository family is "if it can be generated, do not hand-write it; the handwritten
copy drifts".

## 7. What each plane still owes (as of v0.4)

- **Onshape (this plane)**: import capability (the structural gap, delivered as
  `onshape_browser_mode/step_import.py` — plan/dry-run offline, one live attempt gated on a human), plus
  three recording changes. **Done**: the browser STEP manifest now carries a `declaration` block in this
  vocabulary (`onshapescript.handoff/0.4-draft`) that states its own blindness — `kernel`/`measure`/`at`/
  `parts` all null with `readsNothing` in words, a `heuristic` text `solidCount` with its method and
  undercount risk, `tessellation.kind: not_produced_here`, and `sha256_stable: false` with the header
  timestamp as the reason. **Owed**: the tessellation declaration with
  `absolute`/`declared`/`used`/`matches_declaration` on the plane that actually tessellates.
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

## 8. Cross-plane findings (each with the measurement that settled it)

Six findings that are not about the artifact's shape but about how a measurement behaves. Each one changed
a field or a rule, and each one is here because a measurement contradicted an assumption.

### A reading declares the state it was taken in, because an action changes it

Four instances of one defect class, all measured, all in this negotiation:

| Instance | What changed | What the reading should have said |
|---|---|---|
| CadQuery's STL export mutates the shape's cached box (`ymax 380.0000001000 → 380.0008703904` on piece #0) | a measurement taken *after* the export is in no other implementation's family | `boundsAlgorithm` + `boundsAfterTessellationMm` + `boundsMutatedByExport` |
| this repository's self-comparison (both numbers read after the export) | it compared a family with itself and reported "no gap" | compare within a declared family, and report the method gap separately (`boundsMethodGapMm` vs `boundsCrossRunMm`) |
| MeshQ's `inspect` deriving scratch inside the *input* directory | concurrent runs measured the wrong piece | derive into a run-owned directory |
| an expression-resolve wait publishing only `elapsedMs` | a wall-clock reading cannot answer "did the first read settle it?" | publish `reads` (a count) and only bound the clock |

So the rule is not about bounds or waits: **a reading states the action/state it is relative to**, and
where an action can change it, the pre- and post-action values both travel (as this repository now does
for the box). A number without its state is a number with a missing operand — the same defect as a
direction-derived reading without its direction.

### Identical bytes do NOT make every reading agree — so each reading names its algorithm

The 70-piece join is the cleanest available experiment, because the inputs are provably identical: the
two producers' STL files are byte-identical on **70/70** pieces, and both sides report the same exact
B-Rep volume on **70/70** (bit-for-bit, delta `0.0`). Yet:

* the **mesh volume** differs by up to **2.41e-6 relative** on those identical bytes (so it is not a
  geometry difference; it is a difference of algorithm or accumulation, and the field must declare one);
* the **mesh bounding box** differs by up to **1.2207e-05 mm** — and here the bytes decide which side is
  wrong: this repository's field equals the bytes' vertex box on 70/70, CadQ's equals it on 54/70.

The general form: *an identical artifact does not produce identical readings, so a reading is only
comparable at a declared method.* Fields that come from the artifact's bytes are the ones a third party can
check without a kernel; that is why the mesh family is the one that travels for identity.

### Addressing, measured (index vs volume vs tuple vs digest)

From the same join, on CadQ's 70 solids and this repository's 70 pieces:

* **by index** — works, and must never be the identity: the two sides agree on 70/70 exact volumes and
  70/70 STL digests, but an index is an ordering, and a re-export may reorder;
* **by exact volume alone** — cannot address this part at all: **14 duplicate value groups cover 60 of the
  70 pieces**, and the largest group has **8 members** (so volume alone is ambiguous for 86 % of the
  pieces — exactly the assembly that motivated the identity rule);
* **by the identity tuple** (`brepVolumeMm3` + mesh-family `bounds_mm`, quantized as declared) — the two
  sides' multisets are **equal**, 70/70 both ways, with no piece left over on either side. This is the
  selection address;
* **by digest** — for transfer, and with the rule version first: a digest moved between this repository's
  two generations (`ade4c12ab2b91fc5… → 7f4271064f1107bebb3aaaf4…`) with the geometry untouched, because
  the canonical form changed, and MeshQ measured the same thing at CadQ (its set signature moved between
  schema 0.1 and 0.2 while every STL byte stayed the same). Hence `identity_rule.version` (this repository
  publishes `onshapescript.mesh-set-signature/1`) and a peer-side `signature_schema`; **a digest comparison
  starts by comparing rules, never digests**.

### Addressing is now implemented on both legs (digest is the address, path resolves it)

`### Addressing, measured` earlier settled *what* identifies a piece. The transfer itself needed the same
decision one level up, and it now exists in code on both sides:

* **producer** (browser export): `declaration.identity.sha256` with `sha256_stable: false` and the reason,
  plus `identity_rule.version` — the digest addresses *this delivery* and the rule says under what canonical
  form;
* **consumer** (browser import): a declared digest (`expect_sha256`, or `handoff_manifest` reading
  `declaration.identity.sha256` / `artifact.sha256`) must match the file at the path, or the import is
  **refused in the offline plan, before anything touches the page**; a handoff that cannot name its bytes is
  refused by name rather than downgraded to a path lookup; and with no digest declared the record says
  `addressedBy: "path"` instead of implying an address it never checked.

The rule generalises the one that has already been paid for twice in this negotiation: **a path is a
resolution, a digest is an address, and a mismatch is a refusal rather than a coincidence** — the same shape
as "a reading declares the state it was taken in" (the state here is *which bytes*), and as "a tolerance has
a vintage" (the reader set is *when* it was derived).

### The absent-field half of every rule, and why the fixtures hid it

A rule set can be entirely correct field-by-field and still fail open, because "what to do when the field
says X" says nothing about the field being gone. Measured on this repository's own guard (ten adversarial
variants, MeshQ 182):

| Variant | First version | Now |
|---|---|---|
| A the real handoff | accepted ✓ | accepted ✓ |
| B caller prints in another direction | rule 5 ✓ | rule 5 ✓ |
| C `print` block present but all values null | rule 1 ✓ | rule 1 ✓ |
| D the whole `orientation` block deleted, readings kept | **accepted** | rule 2 |
| E `orientation.applicable` null, readings kept | **accepted** | rule 2 |
| F `grade: unknown` with no reason | **accepted** | rule 4 |
| G the producer stamps `printable: true` | rule 3 ✓ | rule 3 ✓ |
| H the per-piece `at` deleted | rule 1 ✓ | rule 1 ✓ |
| I `print: {}` | rule 1 ✓ | rule 1 ✓ |
| J `envelope.declared_by` names the producer | rule 3 ✓ | rule 3 ✓ |
| K the reference point null at both levels | **accepted** | rule 1 |

Two lessons, both about the *tests* rather than the rules:

1. **A fixture that always fills every field cannot see this class.** The guard's own test helper supplied
   `orientation`, `at.reference_point` and `min_wall.reason` on every call, so the absent path was never
   constructed — which is exactly the shape of "the test pins the weakness" seen earlier, one level up: the
   first pins a weak value, this one never builds the weak path.
2. **Per required field, build one fixture with the field absent** (and one with it null). That is now a
   practice, not an intention (see §10), and it is why the guard ships with all ten variants as tests
   instead of the ten values it was written for.

This family now has four independent instances, one per plane and one per direction: an `applicable` flag
used as an all-or-nothing gate (MeshQ), a winding check whose welding precondition was forgotten (CadQ),
a field name that over-claimed what it computed (`outwardOriented`, this repository), and this guard whose
rules evaporated on deletion.

### A tolerance is derived from the measured spread across readers, and each quantity names its own precision

The sharpest correction of this negotiation came from a third plane recomputing the readings straight from
the bytes (per-triangle double, `math.fsum`), which turns "who is right" into a table:

| Quantity, max over 70 pieces | onshapescript | CadQ (tessellation) | MeshQ |
|---|---|---|---|
| mesh area, relative | **9.8e-13** (1 ulp) | 4.99e-07 | **3.39e-06** (self-reported; arithmetic, sign-mixed 30/70) |
| mesh volume, relative | **1.08e-12** | **2.41e-06** (independently reproduced) | ≤1.5e-10 (print precision) |
| mesh bounds, absolute mm | **0.0 (70/70 bitwise)** | 1.221e-05 (70/70 > 1e-6) | ≤4.7e-07 (print precision) |

Two rules follow, and both are now in the artifact rather than in prose:

1. **A tolerance is derived from the measured spread across readers, not from the writing plane's own
   accuracy.** An area bound of `1e-6` would adjudicate a *correct* implementation (MeshQ's 3.39e-06) as
   wrong, so this repository publishes `areaMm2: 1e-5` **with the three measurements that derived it**
   (`equivalence_tolerance_basis`), beside `brepVolumeMm3: 1e-6` (justified by a bit-for-bit agreement,
   delta `0.0`) and `bounds_mm: 1e-3` (justified by the declared family's bitwise agreement, with the
   cross-family method gap at `1.2e-5` mm).
2. **A reading is identified by who computed it and how precisely, not only by who defined it.**
   `readings_basis` names, per quantity, the family, the algorithm, and the precision **demonstrated
   against an independent recomputation** ("1.08e-12 relative vs an independent per-triangle `fsum`
   recomputation"; "0.000e+00 absolute, bitwise equal to the bytes on 70/70"). That is the third dimension
   of identity, and it is the one that lets a reader decide whether two numbers are comparable at all.

A related reading of the same table: **the arithmetic path is part of the interface.** Two planes can hold
byte-identical geometry and still disagree by `2.4e-06` in volume and `3.4e-06` in area, so "identical
bytes" does not imply "identical readings" — and a plane that publishes a reading without its algorithm is
publishing a number nobody can adjudicate.

### An unevaluated check must not look green

A peer measured this on its own tool (its item 20): `inspect <part> --checks overhang --expect-volume 1` — an
expectation declared for a check that was not requested — exits **0**, and the human-facing summary prints
`"verdicts": {"part-0000": {"_failed": []}}`, while the record's own `_summary` says
`{"checks": 0, …, "inert_rules": ["expected_volume_mm3"]}`. Its root cause is that the summariser copies each
object's `{name: pass}` and `_failed` and **never copies `inert_rules` or `check_errors`**. As it put it: **an
expectation that was never evaluated is not even a hole — it looks like all-green.** (Recorded here as a
*reproduction*, not a landing: it has not changed its code.)

The same shape existed one level down in this repository, found by asking the peer's question of our own guard:
`check_print_basis(manifest)` without a caller build direction **cannot run rule 5**, cannot refuse anything
through it, and so returned `ok: true` with the same note as a full run — and this repository's own consumer
tool printed `PASS` on top of it. An unevaluated rule and a passed rule were indistinguishable in the output.

The rule:

* **a check reports what it ran and what it did not run**, and the not-run part carries the reason and the way
  to close it — `ok` is never the verdict, `complete and ok` is;
* a consumer-facing verdict may not print a bare pass when part of the check did not run: it prints
  `INCOMPLETE`, names the rule, and fails, unless the caller **says out loud** that a partial check is what it
  wants (`--declaration-only`, whose verdict reads `PASS (PARTIAL, …)`);
* the failure mode has a name worth keeping: **an expectation that was never evaluated is not a hole, it is a
  green light** — the third member of the family whose other two are "an absent field must be as loud as a
  false one" and "a judgement must reach the machine-facing outcome".

Landed here in `fdm_analysis/conversion/print_basis.py` (`complete` / `rulesRun` / `rulesNotRun`, and the note
now says `INCOMPLETE … so \`ok\` is not a pass`) and in `dev/tools/check_handoff.py` (exit 1 for an incomplete
run with the rule, the reason and the way to close it; `--build-direction` closes it, `--declaration-only`
accepts it explicitly). Tests: `test_a_rule_that_did_not_run_is_named_and_ok_is_not_a_pass`,
`test_a_rule_that_did_not_run_is_not_a_pass`, and `test_declaring_the_partial_check_is_the_only_way_it_reads_as_a_pass`.

### "I am not a gate" must be written in your own output

The plane that found the empty-probe rule added this boundary to the same family: a warning-level checker
**can be used as a gate by whoever reads it**, and if its output does not say that it is not one, it becomes a
defect **through a sentence it never said**. A boundary that lives only in a module docstring is a boundary
the reader never sees.

The rule: **a check that does not block must say so in the artifact it produces** — in the payload for the
machine and in the printed text for the human — and must also say what its exit code means, because "1" is
read as "forbidden" by default.

Applied here (2026-10-03): this repository's local FeatureScript check had a summary line that read
`structural errors MUST be fixed before upload (they waste quota)` — advice phrased as a directive, with no
statement of the boundary, while the machine-facing payload already carried `advisory: True`. The summary now
says the findings are worth fixing **and** that the check is advisory, that it never blocks an upload, and that
exit code 1 means "structural findings were found", not "the upload is forbidden" — the deploy path decides, and
a deploy that would write error-level findings asks for an explicit acknowledgement instead of being vetoed
here. The regression test asserts the three phrases **and** that the old wording does not come back.

This is also the clean statement of the criterion the same plane proposed for telling a design decision from a
defect: **is it used as a gate?** A warning-level finding that is never a gate is a design choice; the moment
someone treats it as one, it is a defect — which is exactly why the boundary has to be in the output.

### An empty probe is a phenomenon, not evidence

This is the third instance of the probe-cleanliness rule, and it came from the plane that asked for the rule:
checking this repository's self-audit, it ran one `grep` that was **truncated by `head`** and passed a **guessed
path** — so it got no output, and no output read as "that file does not exist". It did exist. The clean re-run
found it.

The general form, which is the same shape as "a missing row is not absence":

* **an empty or partial probe result is a phenomenon to be explained, not evidence** — "absent", "not looked
  at", "looked at the wrong place" and "the output was cut off" must be distinguishable in the probe itself;
* a probe that cannot tell those apart must report `unknown` with its reason, never a negative verdict.

Three instances already in this repository, each with the measurement that produced it:

* the Part Studio feature read publishes `headerCount` next to `ready` / `rowsComplete`, because the list is
  virtualised and renders only a window: **a missing row is not absence** (the tool description says so);
* the STEP import refuses with `before_read_failed` when its before-read fails, instead of judging landing
  against an empty row list — "an empty row list" and "a page that could not be read" are different facts, and
  the test asserts nothing was clicked in that case;
* the browser export leg's solid count reports `grade: "unknown"` **with a reason** when the recorded artifact
  cannot be re-read, rather than returning 0 (which would look like a clean measurement).

So the family now has three members, all paid for: **a missing field must be as loud as a false one**
(field-level), **a judgement must reach the machine-facing outcome** (code-path level), and **an empty probe
must be distinguishable from an unread one** (measurement level). Each one was found because a party asked
"what does this absence actually mean?" instead of accepting it as a value.

### Failures must close: one judgement, every entry point

A third plane found this by asking the inverse of "does the gate say no?" — namely **"when the rule says no,
does anything else hear it?"** Measured on its own tool (MeshQ 189 §3):

```
job: inspection.rules {max_overhang_area_mm2: 0.0}, measured 67.85130525 mm²
  → the record carries verdicts … pass: false, with measured/limit in the detail
  → exit code = 0                                  ← the `run` entry point
the same part with a deliberately wrong expectation  → exit code = 1   ← the `inspect` entry point
```

Root cause read from the source rather than inferred: `run` derives `failed` only from
`--expect-max-deviation` and never looks at `inspection.verdicts`, while `inspect` walks the verdicts. Both
entry points wrote their own copy of the same judgement, and one copy is missing. It then propagates to the
agent-facing surface, whose outcome mapping reads the subprocess exit code — so the call returns
`exit_code: 0` / `outcome: "ok"` / `failed: false` **in the same payload as a record that says
`pass: false`**.

The rule, in the general form this negotiation keeps rediscovering:

* **a judgement must be mapped into the machine-facing outcome, once per entry point, and every entry point
  must do it** — a judgement computed and then dropped is worse than no judgement, because it reads as a
  green light;
* the failure mode has a shape worth naming: **one judgement, two call sites, one copy missing.** It is the
  absent-field lesson one level up — the missing thing is a code path rather than a field, and it is just as
  invisible;
* the guard against the shape is not "more code" but **one implementation with several callers** (then there
  is no second copy to drift), plus a test per entry point that a failing rule changes that entry point's
  outcome.

Self-audit of this repository against that rule (2026-10-03): the shape *does* exist here — the project-docs
index digest is checked both by `onshape_docs/verification/verify_docs.py` and by
`dev/tests/test_docs_index_digests.py` — but both call the single `onshape_docs/query/source_digest.text_sha256`,
so there is one implementation with two callers and no second copy to fall out of step. Measured the same day:
a stale page digest made **both** entry points fail together (`verify_docs.py` 16/17 and
`test_project_docs_index_pages_match`), which is what "one implementation, two callers" looks like when it
works. Two checkers in this repository already close their failures (`verify_docs.py` returns 1 on any failed
check; `build_tool_reference.py --check` returns 1 when the generated reference is missing or stale), and the
one place where a failing finding deliberately does **not** change the exit code is the FeatureScript local
check, which is warning-level by an explicit project decision rather than by omission — the difference
matters, because the first is a design choice and the second is a bug.

The threshold's **range** belongs to the same round: the guard now refuses a threshold outside
`0 < threshold_deg <= 180` at both levels, because outside it an overhang reading is not looser or stricter but
meaningless (`0`, `181`, `1e9`, `-45` all passed the version that only asked for presence and finiteness;
`0.001`, `45`, `90` and `180` still pass, and the real 70-piece handoff is still accepted with 0 refusals).

### A tolerance has a vintage, and a value has a kind

Two additions from the third round of adversarial review, both about a bound or a value being *stale or
mistyped* rather than absent.

**A tolerance has a vintage.** `equivalence_tolerance_basis` says where a number came from; it does not say
*whom it was derived for, or when*. `areaMm2: 1e-5` was derived from one reader set on one day (this
repository `9.8e-13` / CadQ `4.99e-7` / MeshQ `3.39e-6`), and freezing that number does two harmful things:
it stays looser than necessary once the loosest reader tightens, and — worse — it silently admits a future
reader that is just as loose, which defeats the only reason the bound exists (not to fail a *correct*
reader). So `equivalence_tolerance_vintage` names the reader set, the date, the witness, and the
re-derivation condition ("any listed reader changes its algorithm or its printing precision"), and the
consumer-side checker refuses a declared tolerance that has no vintage at all. This is the same lesson as a
reading declaring the state it was taken in, one level up: **a reading declares its state; a bound declares
its readers.**

**A value has a kind.** The print-basis guard's first hardening refused an absent or `null` verdict and a
literal `False`, which left every value in between passing — so a producer that declared "not applicable"
with a JSON `0` or the string `"false"` obtained a pass, i.e. **the rule was inverted by a type**. The same
round caught a validator that converted with `float()` and then ran `isinstance` over its own conversion, so
that half could never fail: `["0","0","1"]`, `[0,0,True]` and `[0,0,inf]` all passed while the message
claimed to require three *finite* numbers. Two rules follow: a required boolean must be **literally** `true`
at a gate (a truthy substitute is a refusal, and an honest `false` gets a different, accurate reason), and
**a raw value is validated before it is converted** — validation that runs after conversion is not
validation. The reviewer also reported that its own NaN probe was unclean (one reused list object, where
CPython's comparison takes an identity fast path), so NaN is now tested rather than assumed, and the
unclean result was left out of its conclusions rather than promoted.

### The evidence axes are two, not one

`unknown` means **not computed here** (a gap, and it must carry a reason); `visual` means **the evidence is
a picture a human must read**; a reading that an analyzer *does* compute with declared parameters is
`heuristic`, never `visual`. Conflating the first two loses the difference between "we skipped it" and
"you have to look at it" (MeshQ 179 §4.1). The same distinction decides readings versus verdicts: an area
is a reading, `centerOfMassStable` is a verdict (it joins a model fact to a geometric criterion), so the
criterion is published and a bare `stable: true` is not.

## 9. Does this need a router between the planes? (and who owns the schema)

**Position: no router process, and the reason is this repository's own measured precedent rather than a
preference.** Two findings decide it, and both are already paid for.

### 9.1 A hop must buy a capability, or it is deleted

`browser_invoke_discovered` was demoted for exactly this, in this repository's own audit
(`docs/architecture/TOOL_SURFACE_AUDIT.md`): *"any registered tool is callable by the exact name
`mcp_tool_catalog` returns, so this envelope adds a hop and no capability"*. Its sibling
`mcp_tool_invoke` was **kept**, because it does buy one (a real MCP client refused an unadvertised
registered name with `unknown tool`, 2026-09-21). So the local rule is not "hops are bad": it is **a hop
must add a capability that cannot be obtained at the endpoints**. A cross-plane router would have to answer
the same question, and on today's evidence every candidate answer fails:

* **Schema translation?** Both sides now publish the same field names with declared algorithms
  (`boundsAlgorithm`, per-quantity quanta, `applicable`, `gradeTiers`). Where they disagreed, the fields
  were fixed on both sides instead of a translator being added — and that is strictly cheaper, because a
  translator is a second implementation of a rule that then has to be kept in step (the defect class the
  audit names as the most expensive one).
* **Identity resolution?** A consumer holding an artifact can verify it itself: per-piece digests, the
  declared identity rule, and the exact value quanta. A router would be a third party asked to confirm
  something the holder can measure.
* **Whole-job orchestration?** That capability exists and is named: capability cards
  (`mcp_main/win/mcp/tool_catalog.py` `capability_section`, the L6 "one job, not a tool chain" pattern)
  invoke a job through one registered tool instead of routing between planes.

### 9.2 A router would become a second owner of state that must have one owner

The Onshape MCP runtime policy requires a single modifying agent while scoped document leases are
unverified, and `mcp_tool_catalog` states plainly that its classifications "do not provide multi-call
workflow isolation". A cross-plane router would sit between three planes' browser/profile/quota state and
would have to own target selection, mutation, shared-state sync and cleanup for whichever leg it drives —
i.e. it would become the owner of state this policy says must have exactly one. Rejected for that reason,
not for latency.

### 9.3 The boundary of the position (what would change my mind)

A router becomes justified when at least one of these is true, and none is today:

1. a workflow needs **cross-plane transactionality** — one abort must undo a step another plane already
   took (today every leg is independently verifiable and independently abandonable);
2. the planes must share a **quota or session ledger** that cannot be reconstructed from each plane's own
   receipts (today each plane's ledger is local and read-only to the others);
3. **more than one modifying plane** acts on the same target (today one plane modifies; the others read
   the artifact or the bytes).

Until one holds, the contract is: **exact artifact identity + declared field vocabulary + capability cards
for whole jobs**, and no process in the middle.

### 9.4 Schema ownership, field by field

Ownership follows *who can measure it*, not who writes the document:

| Field group | Owner | Why |
|---|---|---|
| unit, model coordinate system, exact B-Rep readings, per-solid identity | the producer (CadQ) | it is the only plane that holds the exact geometry |
| `measure.kind`, kernel + kernel string convention, tolerance declaration/`used`/`matches_declaration` | the tessellating producer | it performed the tessellation and knows the call it made |
| mesh-family geometry readings, winding (+`applicable`), `boundsAlgorithm`, `gradeTiers` | the measuring plane (onshapescript, MeshQ) | it computed them from the bytes, by a method it must name |
| build direction, threshold, reference point | the measuring plane, declared per artifact | the readings are functions of them (MeshQ 151 §C) |
| envelope, minimum wall, and any printability verdict | the consumer | machine state and acceptance are not geometry |
| the schema **version string** | whoever changes a refusal rule, and it is a breaking-change signal | proven: `handoff_schema: onshapescript.handoff/0.3-draft` in a v0.4 implementation is exactly how MeshQ caught the drift, because that field is the gate a consumer uses to refuse an artifact it does not understand |

The document itself may live in both repositories (MeshQ keeps its own manifest, this repository keeps
this draft); what may not diverge silently is the **version string** and the **field-level ownership**
above.

## 10. Cross-plane collaboration practice (what actually worked, and what it cost to learn)

Not principles — practices, each with the incident that produced it. This is the part of the negotiation
that is portable to any future plane.

1. **Verify with a different *method*, and say which kind of independence you have.** Three levels, and
   they must not be confused: a different kernel (real geometric evidence), a different implementation on
   the same kernel (catches implementation drift, and is what "byte-identical 70/70 + exact volume
   bit-identical" actually shows here), and the same code run twice (proves nothing new). Every artifact in
   this negotiation carries `independent_kernel: false` plus a note, on both sides, for exactly this reason.
2. **Report the per-piece maximum and the worst piece, never the aggregate alone.** One batch agreed to
   `1.31e-7` in aggregate while its worst piece disagreed by `3.39e-6` — a factor of 26 hidden by
   cancellation (MeshQ, and its own earlier message reported the aggregate).
3. **Every field declares its family and its algorithm.** `bounds_mm` had four implementations and four
   answers (max gap `3.19e-2 mm`); the fix was not a looser tolerance but a declared family per field.
4. **Every reading declares the state/action it was taken in.** `cq.exporters.export` mutating the cached
   box, a self-comparison over two post-export numbers, a scratch file derived inside an input directory,
   and a wait publishing only `elapsedMs` are one defect class (see §8).
5. **The bytes are the referee for a delivered artifact.** Two producers' STL files byte-identical
   piece-for-piece settle which of two bounds fields is wrong (`399.9` vs its own bytes'
   `399.8999938964844`), with no kernel needed in the loop.
6. **Publish counts and denominators, not only clocks and aggregates.** `checkedEdges = 3·triangles/2`
   (= 1566 here) is what proves a winding check ran on a welded graph; `reads` answers a question
   `elapsedMs` cannot; `contributingPieces` stops a total from hiding a piece that dropped out.
7. **A retraction is a deliverable, and it belongs in the artifact, not only in the chat.** Both planes
   retracted real claims with the measurement that killed them: a scratch file derived into an input
   directory made 45 of 70 rows wrong; an earlier ramp measurement (`overhang 0 → 565.19`) was withdrawn
   and superseded; a suspected peer defect was checked and **disproved** (the peer's exact box equals the
   pre-export one, delta `0.0` on 70/70) and corrected in the record.
8. **Do not create a competing delivery.** When one plane has already delivered and been read, a second
   copy of the same artifact is a liability; the useful second artifact is a *verification* record, and its
   directory says so in a `PURPOSE.md` that names the producer's copy as the authority.
9. **Adopt the peer's vocabulary verbatim instead of inventing a parallel one.** MeshQ's `grade_tiers`
   (`reliable`/`heuristic`/`visual`/`unknown`) is now implemented in this repository's analyzer with its
   source cited, so one word means one thing in both places.
10. **A fixture is a real artifact with a stated purpose and honest provenance.** Two probes exist for the
    winding question: one built correctly, and one that came out degenerate through an offset mistake —
    kept, labelled with how it was made, and it is the one that exposed the vacuously-consistent defect.
11. **Version the rule, not only the artifact.** A rule change moves a digest while the geometry does not
    (this repository: `ade4c12a… → 7f427106…`; CadQ: its signature moved between schema 0.1 and 0.2 with
    every STL byte unchanged), so comparisons start at the rule (`identity_rule.version`,
    `signature_schema`) and never at the digest.
12. **A delivery is not a receipt, and neither is your own ledger.** The mailbox tool distinguishes
    "landed in the project" (`found`) from a recipient ack (`签收 n/m`), and a hop is only closed on the
    second. This cut both ways in practice: the ack command's *return line* is not the receipt either —
    four messages this repository believed it had acknowledged (169, 170, 164, 173) still read `0/1` when
    the receipt tool was asked, and only a re-run of the ack moved them (`169 → 1/1`, `170 → 1/2` with
    this repository as the 1). The rule that follows is the same one this repository applies to its own
    `send`-style tools: **never carry a claim of receipt that the receipt tool would not confirm**, and
    after any ack, re-ask the tool rather than the memory of having seen a confirmation line.
19. **An unevaluated check must not look green.** Report what ran and what did not, with the reason and the
    way to close it; `ok` is not the verdict, `complete and ok` is; a consumer-facing pass may never be printed
    for a partial run unless the caller says out loud that a partial run is what it wants. (Instance: a guard
    silently skipped the one rule that needed a caller-supplied direction, and the tool printed PASS on top of
    it — while a peer found the same shape in its own summariser, where an unrequested expectation printed as a
    green summary.)
18. **A check that does not block must say so in its own output** — in the payload and in the printed text,
    along with what its exit code means. A boundary kept only in documentation is a boundary the reader never
    sees, and a warning-level check nobody warned about becomes a defect through a sentence it never said.
17. **An empty probe result is a phenomenon, not evidence.** Say which of "absent", "not looked at" and
    "output truncated" produced the emptiness, and report `unknown` with a reason when you cannot; a probe
    that cannot tell those apart has not measured anything. (Instance: a truncated `grep` plus a guessed path
    produced empty output for a file that exists — and empty read as non-existence.)
16. **Every entry point maps the verdict to the outcome.** A judgement computed in one place and dropped in
    another is worse than no judgement, because it reads as a green light — ask the inverse question "when
    the rule says no, who hears it?" for every entry point, and prefer one implementation with several
    callers over several copies of one judgement.
15. **Test the kind, not only the presence.** One fixture per required field with the *wrong type* and
    one with a *non-finite* value: a field of the wrong kind looks filled in, so it is harder to notice than
    a hole, and a validator that converts before it checks has already lost the information.
14. **Test the deletion, not only the value.** Every required field gets one fixture with the field
    absent and one with it null, because a fixture that always fills them proves nothing about the path
    where they are gone — four of ten adversarial variants passed this repository's own guard for exactly
    that reason.
13. **Refusals are the interface.** Every conclusion above is written as something a consumer can refuse
    (rules 1-17), because a shared contract that cannot say "no" is a convention, not a boundary.

### The consumer's half of the identity rule (implemented)

`fdm_analysis/conversion/identity_check.py::check_identity_against()` is the counterpart of the print-basis
guard, and the check the import leg needs before anything downstream trusts a converted artifact. Given a
handoff and the readings a consumer took on what it holds, it reports per quantity: status, both values, the
difference, the declared tolerance and **the measurement that derived that tolerance** — or a refusal,
naming which rule and what to fix. Four properties are deliberate:

* **units are checked first and a mismatch is a refusal, not a scale factor** (an inch-vs-mm import is a
  silent 25.4x change, and a 25.4x error inside a tolerance comparison reads as a correct transfer);
* **the tolerance comes from the manifest, never from the checker** — and a tolerance with no
  `equivalence_tolerance_basis` entry is refused, because a bound that only fits its author fails correct
  peers;
* **the rule precedes the digest**: a `identity_rule.version` mismatch returns `not_comparable` instead of
  reporting a difference;
* **per-piece quantities report the per-piece maximum, the worst piece index, the outside count and a
  bounded list of the offenders**, never an aggregate alone; and a bounds comparison is only made inside the
  `bounds_family` the rule declares (an undeclared family is `not_compared`, not a guess).

It also carries the single mapping between the rule's quantity names and the artifact's field names
(`brepVolumeMm3` ↔ `brep.volume_mm3`), because the boundary has two naming systems and §2d row 10 already
decided that there is exactly one mapping at the boundary.

Measured: run against the **real 70-piece handoff** with its own readings it accepts and compares 70/70
pieces with 0 outside; shift every volume by 0.1 % and it reports 70 outside with the worst piece named.
Eight tests in `dev/tests/test_identity_check.py`, one of which skips itself when the drop directory is
absent so the suite stays offline-clean.

## 11. Evidence

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
| A bounding box is not one measurement | MeshQ 170 §3 (four families, max gap 3.19e-2 mm) plus this repository's measurement of `cq.exporters.export` mutating the cached box (`ymax 380.0000001000 → 380.0008703904`) |
| A consistent winding over a broken edge graph is vacuously consistent | `/tmp/three-plane-drop/onshapescript-degenerate-piece-probe/manifest.json` (degenerate triangle → `watertight: false`, `nonManifoldEdges: 1`, `consistent: true`) and its sibling `onshapescript-flipped-piece-probe/` (a real flipped winding: `consistent: false`, area unchanged at 464.320189554 mm², volume and overhang `null` with `applicable: false`) |
| Per-piece max beats the aggregate | The same 70-piece batch: aggregate 1.31e-7 vs per-piece maximum 3.39e-6 (26×), worst piece #20 |
| A hop must buy a capability | `docs/architecture/TOOL_SURFACE_AUDIT.md`: `browser_invoke_discovered` (`Internal-only`, "adds a hop and no capability") vs `mcp_tool_invoke` (kept, because a real client refused an unadvertised name with `unknown tool` on 2026-09-21) |
| A router would be a second owner of single-owner state | `mcp_tool_catalog` status text ("classification does not provide multi-call workflow isolation") + the Onshape MCP runtime policy's single-modifying-agent requirement while scoped document leases are unverified |
| The bytes are the referee | 70-piece join: STL bytes identical 70/70; this repository's mesh box equals the bytes 70/70, CadQ's 54/70 (gap 1.2207e-05 mm, e.g. its `399.9` vs its own bytes' `399.8999938964844`) |
| Identical bytes, non-identical readings | Same bytes: mesh volume differs up to 2.41e-6 relative; exact B-Rep volume agrees bit-for-bit 70/70 (delta 0.0) |
| Volume alone cannot address this assembly | 14 duplicate volume groups covering 60/70 pieces, largest group 8; the (volume, mesh bounds) tuple matches as a multiset 70/70 across producers |
| A digest names its rule | `identity_rule.version` = `onshapescript.mesh-set-signature/1`; CadQ publishes `signature_schema: cadq.brep-signature/2`; MeshQ 168 measured a signature move with byte-identical geometry |
| A tolerance must come from the reader spread | MeshQ 179 §3 referee table (area 9.8e-13 / 4.99e-7 / 3.39e-6 on byte-identical input) → `equivalence_tolerance` + `equivalence_tolerance_basis` (`areaMm2: 1e-5`), and `readings_basis` per quantity |
| Addressing needs both halves, in code | Producer: `declaration.identity.sha256` + `sha256_stable: false` + `identity_rule.version` in the staged browser STEP manifest. Consumer: `expect_sha256`/`handoff_manifest` in `onshape_browser_mode/step_import.py`, mismatch refused offline before any click, handoff without a digest refused by name, `addressedBy: "path"` recorded when nothing was declared (23 tests) |
| Unevaluated checks must not look green (round 4) | Peer reproduction recorded (its item 20: `--checks overhang --expect-volume 1` exits 0 with `_failed: []` while `_summary.inert_rules` names the expectation); **landed here**: `check_print_basis` returns `complete`/`rulesRun`/`rulesNotRun` with the reason and the way to close each skipped rule, and `dev/tools/check_handoff.py` exits 1 for an incomplete run unless `--declaration-only` is passed, whose verdict reads `PASS (PARTIAL, …)` |
| "I am not a gate" is written in the output | MeshQ 194 §3 (its boundary rule): this repository's local FeatureScript check printed `structural errors MUST be fixed before upload` — advice phrased as a directive — while its payload already carried `advisory: True`; the summary now states the boundary and what exit 1 means, and `dev/tests/test_static_guards.py::test_the_cli_says_in_its_own_output_that_it_is_not_a_gate` asserts the three phrases plus the absence of the old wording |
| An empty probe is a phenomenon, not evidence | MeshQ 192 §2: one `grep` truncated by `head` against a **guessed** path returned empty for a file that exists, and empty read as "does not exist"; the family's three internal instances are recorded with the measurement behind each (virtualised feature list publishing `headerCount`/`ready`/`rowsComplete`; the import leg's `before_read_failed` refusing instead of judging against an empty row list; `_solid_count` reporting `unknown` + reason rather than 0) |
| Failures must close — one judgement, every entry point | MeshQ 189 §3 measurement (`run` exit 0 while `inspection.verdicts` says `pass: false`; `inspect` exit 1 for the same shape) recorded with its root cause read from the source; this repository's self-audit finds the duplicate-judgement shape (docs index digest in `verify_docs.py` and `test_docs_index_digests.py`) but **one implementation with two callers**, proven by both failing together on one stale digest |
| The threshold range is part of rule 1 | MeshQ 189 §3: `0`, `181`, `1e9`, `-45` passed this guard's first version; now refused at both levels with the range named, endpoints `0.001`/`45`/`90`/`180` still accepted, real 70-piece manifest still 0 refusals (`test_a_threshold_outside_its_only_meaningful_range_is_refused`) |
| A tolerance has a vintage; a value has a kind | MeshQ 185 §1 / 187 §2–3: `equivalence_tolerance_vintage` (reader set + date + witness + re-derivation condition, required by `check_identity_against`); rule 2 requires a *literally* true verdict (`applicable: 0` and `"false"` passed the previous version), and the direction/threshold validators check the RAW JSON value before converting — `["0","0","1"]`, `[0,0,True]`, `[0,0,inf]`, `[0,0,NaN]` are all refused, pinned by `test_a_truthy_substitute_does_not_pass_for_a_winding_verdict` and `test_the_raw_value_is_validated_before_it_is_converted` |
| The identity rule needs a consumer-side checker | `fdm_analysis/conversion/identity_check.py` + `dev/tests/test_identity_check.py` (8 tests, one against the real 70-piece handoff): units first, tolerance from the manifest with its basis required, rule before digest, per-piece maximum with worst piece, bounds only inside the declared family |
| An absent field must be as loud as a false one | Ten adversarial variants against the print-basis guard: six blocked, four passed silently (deleted `orientation`, `applicable: null`, a silent `unknown`, two null reference points) — all four refused after rule 18, pinned by `test_the_field_is_absent_paths_are_as_loud_as_the_false_ones` and `test_the_ten_adversarial_variants_have_the_outcomes_meshq_measured` |
| A retraction belongs in the artifact | MeshQ's `inspect` scratch-in-input-directory pollution (45/70 rows wrong) is recorded as a practice, not hidden; this repository's withdrawn ramp result is superseded in place |
| Path is not identity, digest is (for transfer) | MeshQ message 164 §4: the same 70 piece files read under two different directory names gave **70/70 identical digests**, so a renamed artifact is the same artifact; and the same message shows why a digest still cannot be content *identity* (the STEP header case) |
| Winding-dependence is a property of the reading, not of the field name | MeshQ message 163 §B (three variants, `surface_area_mm2 = 2400.0` throughout) against this repository's retracted ramp (counted overhang area 0.0 → 565.192416792 on a winding flip) |
| Declaration vs acceptance gate, measured on the real fixture | CadQ message 156: 0.3 rad → 0.103 % volume error (fails MeshQ's 0.05 % gate, 12/70 pieces), 0.1 rad → 0.012 % (passes), linear 0.05 → 0.02 mm bit-identical |
| 70-piece tessellation, two implementations reading one handoff | `onshape_docs/verification/interop-70piece-tessellation-2026-10-03.md`: 0/70 triangle-count mismatches (617748 three ways), 0/70 winding disagreements, overhang aggregate agreeing to 1.31e-7, and 70/70 byte-identical STLs across two tessellation runs |
| Overhang face-off, both directions | `onshape_docs/verification/interop-overhang-faceoff-2026-10-03.md` (relative differences 1.77e-8 / 2.0e-8 / 3.5e-9; both sides low by 4.9e-5 against the sphere's closed form), including the retraction of my own first probe set |
| Import request shape | vendored OpenAPI `createTranslation` + `BTBTranslationRequestParams`; `dev/tests/test_rest_step_import.py` cross-checks every sent and unsent field against that schema |
