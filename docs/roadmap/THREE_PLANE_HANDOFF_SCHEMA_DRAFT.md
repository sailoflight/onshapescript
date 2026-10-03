# Three-plane handoff manifest — schema draft v0.2

**Status: v0.2, folded in the first field-level review.** v0.1 was reviewed over the `agent-infra`
mailbox by `WindyIvy`/CadQ (8 field comments, message 123) and `RoseStork`/MeshQ (3 field
disciplines plus 2 measurement rules, message 120). Every accepted change is listed in §2b with the
sender and the reason, including the one direct conflict between the two reviewers and how it was
resolved. Nothing here is implemented behavior yet; per this repository's governance, unimplemented
ideas live in `roadmap/`. The capability matrix, the gaps and the boundary positions are in
`THREE_PLANE_GEOMETRY_INTEROP.md`; this file is only the artifact shape those three planes would
exchange.

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

## 2. The shape (v0.2)

```jsonc
{
  "schema": "onshapescript.handoff/0.2-draft",   // namespaced id + version; an unknown version MUST be refused
  "produced_by": {"plane": "onshape|cadq|meshq", "identity": "<mailbox name>", "tool": "<tool>", "at": "<ISO8601>"},
  "source":      {"kind": "onshape_document|file", "reference": "<url or path>", "identifiers": {}},
  "units": "mm",                                  // THE only place the unit appears; never inferred from a round trip
  "authority":   {"brep": "authoritative", "mesh": "derived",
                  "order": ["brep", "mesh"],      // machine-checkable priority, not prose
                  "statement": "<one sentence, for a human>"},

  "declaration": {                                // REQUIRED block
    "artifact":  {"role": "canonical|derived", "path": "", "media_type": "", "byte_count": 0},
    "identity":  {"sha256": "", "sha256_stable": false,
                  "sha256_stable_evidence": null, // REQUIRED when stable is true: two digests of the same input
                  "sha256_note": ""},
    "geometry":  {
      "measure_kind": "brep_exact|tessellation",  // how the numbers below were obtained
      "kernel": "occt|blender|...",               // which engine produced them
      "solid_count": 0,
      "parts": [{"index": 1, "name": "", "label": null,
                 "bbox_mm": [0,0,0,0,0,0], "volume_mm3": 0.0,
                 "cross_plane_ref": {"export_id": "", "index": 1, "signature": "<optional digest>"}}],
      "identity_rule": {"sort_by": ["volume_mm3", "bbox_mm"], "compare": "relative", "precision": 1e-6},
      "producer_command": "<the exact command that measured this>",
      "measured_tolerance_mm": null               // ONLY for measure_kind = tessellation
    },
    "tessellation": {"linear_tolerance_mm": 0.05, "angular_tolerance_rad": 0.0873, "absolute": true,
                     "declared_by": "<plane>", "used_by": "<plane>",
                     "declared": {"linear_tolerance_mm": 0.05, "angular_tolerance_rad": 0.0873},
                     "used": {"linear_tolerance_mm": 0.05, "angular_tolerance_rad": 0.0873},
                     "matches_declaration": true, // producer-computed; false must be visible, never quiet
                     "read_back_from": "<record the declaration was read back from>",
                     "read_back_at": "<ISO8601>",
                     "kernel": "<kernel + version>"}
  },

  "reference": null,                              // OPTIONAL block: B-Rep readings kept as the truth to
                                                 // compare against, never as an input to a mesh verdict
  "cost": {"where": {"network": "offline|browser|live", "estimated_requests": 0, "mutating": false,
                     "spent_quota": 0, "quota_remaining": null},
           "what":  {"kind": "report|artifacts|executes|control"}},
  "next_action": {"kind": "none|awaiting_peer|fix_backend|needs_human", "detail": ""}
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

## 3. A real instance, generated from real records

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
  "schema": "onshapescript.handoff/0.2-draft",
  "produced_by": {
    "plane": "onshape",
    "identity": "RoseElm",
    "tool": "browser_export_step",
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
    "brep": "authoritative",
    "mesh": "derived",
    "order": [
      "brep",
      "mesh"
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
      "measure_kind": "brep_exact",
      "kernel": "occt",
      "solid_count": 4,
      "parts": [
        {
          "index": 1,
          "name": "solid_01",
          "label": null,
          "bbox_mm": [
            -18.6,
            -18.6,
            0.8,
            18.6,
            18.6,
            2.6
          ],
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
          "bbox_mm": [
            -20.75,
            -20.75,
            2.6,
            20.75,
            20.75,
            4.75
          ],
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
          "bbox_mm": [
            -20.75,
            -20.75,
            4.75,
            20.75,
            20.75,
            32.4
          ],
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
          "bbox_mm": [
            -18.6,
            -18.6,
            -0.0,
            18.6,
            18.6,
            0.8
          ],
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
          "bbox_mm"
        ],
        "compare": "relative",
        "precision": 1e-06,
        "set_signature_sha256": "6ba0265e063c75413b41ec0df7871c6b0c4a176d1d9cf201364357f309dcc83a",
        "note": "the digest is a fast path; if two digests differ, compare with the rule above instead of concluding"
      },
      "producer_command": "cadquery_interference.py --mode aabb --linear-tolerance-mm 0.05",
      "measured_tolerance_mm": null
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

## 6. Naming: closed in v0.2

This repository's existing manifests are `camelCase` (`schemaVersion`, `byteCount`,
`linearToleranceMm`) while MeshQ's proposed cross-plane names are `snake_case`. Both reviewers
supported the same resolution: **the cross-plane file is snake_case, with exactly one mapping at the
handoff boundary.** CadQ's internal identifiers are already snake_case, so it needs no mapping;
the alternative ("keep camelCase and let every consumer translate") would produce two translators
for one field, which is the failure this rule exists to prevent. The mapping lives in this
repository, once, next to whatever produces the file.

## 7. What each plane still owes (as of v0.2)

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
| Import request shape | vendored OpenAPI `createTranslation` + `BTBTranslationRequestParams`; `dev/tests/test_rest_step_import.py` cross-checks every sent and unsent field against that schema |
