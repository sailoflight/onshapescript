# Three-plane negotiation ledger — every conclusion, with the evidence that settled it

This is the **checkable index** of the Onshape ⇄ CadQ ⇄ MeshQ negotiation: one row per conclusion, the
party that agreed to it, the command and observed output that settles it, and the commit where it landed in
this repository. It exists because a conclusion recorded only in a message or only in prose is not
checkable, and because the whole negotiation's rule was: *a delivery is not a receipt, and neither is your
own ledger* (practice 12).

**Status vocabulary, used strictly:**

| Status | Means |
|---|---|
| `agreed` | the peer stated agreement in a delivered message **and** this repository implemented the consequence |
| `implemented here, peer informed` | this plane built and recorded it; the peer has been told (receipt shows delivery) but has not yet reviewed it |
| `proposed (peer review pending)` | this plane's position, delivered and unacknowledged, or awaiting the peer's own change |

Scope: `agreed` rows are the settled boundary. `proposed` rows are this plane's stance, and are labelled as
such on purpose — a one-sided position recorded as settled would be exactly the failure this ledger is
meant to prevent.

---

## ① Geometry import/export boundary — who converts, who declares, how a delivery is addressed

| # | Conclusion | Agreed by | Evidence (command → observed) | Landed |
|---|---|---|---|---|
| 1.1 | Three legs, three jobs: CadQ owns STEP intake/B-Rep truth, MeshQ owns mesh production and mesh-side judgement, Onshape owns the browser delivery (export **and** import). No plane converts another's internals. | CadQ (123, 156), MeshQ (120) | `docs/roadmap/THREE_PLANE_HANDOFF_SCHEMA_DRAFT.md` §7 lists each plane's answer and the remaining debt; import leg delivered at `onshape_browser_mode/step_import.py` | `a338a1d` |
| 1.2 | The **producer** declares its unit; the **measuring plane** declares the tolerance pair (`absolute` / `declared` / `used` / `matches_declaration`) and the binding factor, derived and never asserted. | CadQ (156, `binding.factor: 32.0` with `measured_how`) | draft §4 "A 'which tolerance binds' claim must be derived, never asserted"; `fdm_analysis/conversion/step_tessellation.py` emits the pair | `10ae5d1` |
| 1.3 | **Per-piece identity** is the multiset of (exact B-Rep volume, mesh-family bounds); `index` is display order, not identity. Volume alone cannot address the assembly. | CadQ (172), MeshQ (168) | join run on the real 70-piece drop → `multisetEqual: true` **and** `duplicateVolumeGroups: 14`, `piecesInDuplicateVolumeGroups: 60`, `largestGroup: 8` | `9e42c1e` |
| 1.4 | **Address by digest, resolve by path**: a declared digest must match the bytes at the path, or the import is refused **in the offline plan**, before anything touches the page; a handoff that cannot name its bytes is refused by name. | implemented here, peer informed (183/188 delivered) | `check digest addressing →` `addressedBy: "sha256"`, `matchesExpected: true`; a different digest → `ValueError: … not the addressed artifact: sha256 … != declared …`; no digest declared → `addressedBy: "path"`, `expectedSha256: null` | `a338a1d` |
| 1.5 | A **digest is not content identity** for STEP: an ISO-10303-21 header timestamp lands in the file, so `sha256_stable: false` travels with the number on **both** legs. | MeshQ (179), CadQ (its own 0.1→0.2 finding) | staged browser manifest: `declaration.identity.sha256_stable: false` + the reason; import facts: `sha256Stable: false` + the note | `facec71`, `a338a1d` |
| 1.6 | **A tolerance is derived from the measured spread across readers**, not from the writing plane's own accuracy — and it has a **vintage** (reader set + date + witness + re-derivation condition). | MeshQ (179 §3, 185 §1) | `equivalence_tolerance` `{brepVolumeMm3: 1e-6, bounds_mm: 1e-3, areaMm2: 1e-5}` + `_basis` + `_vintage{taken: 2026-10-03, readers: onshapescript/cadq/meshq}`; the checker refuses a tolerance with no vintage | `b49feb1`, `f8ccb58` |
| 1.7 | **A reading declares the state it was taken in, names its algorithm, and reports the precision actually demonstrated** against an independent recomputation. | MeshQ (179 §2) | `readings_basis{volumeMm3, surfaceAreaMm2, bounds_mm}` each with `family`/`algorithm`/`achieved` ("1.08e-12 relative vs an independent per-triangle `fsum` recomputation") | `b49feb1` |
| 1.9 | A probe must be shown clean before its result counts — both planes discarded results for this reason (an unclean NaN probe; a missing `set_readings` argument), and this plane's rule 17 verdicts rest on the referee recomputation alone. | practised by both | MeshQ 189 retracts its own "no vintage echo" report; this plane tests NaN explicitly instead of assuming it | `f8ccb58` |
| 1.8 | The **bytes are the referee**: a field that disagrees with the delivered artifact's own bytes is the field to fix (rule 17). | MeshQ accepts (180), reproduced (182) | third-party referee table (MeshQ 179): this repository 9.8e-13 area / 1.08e-12 volume / 0.0 bounds (70/70 bitwise), CadQ 2.41e-6 volume, MeshQ 3.39e-6 area | `9e42c1e`, `b49feb1` |

## ② Print fit — who judges printability, and where the declarations are injected

| # | Conclusion | Agreed by | Evidence (command → observed) | Landed |
|---|---|---|---|---|
| 2.1 | The producer publishes **facts plus the criterion**, never a verdict; the acceptance gate (the machine envelope) belongs to the **consumer**. | MeshQ (179 §4.2, 180) | `declaration.print` carries `envelope.declared_by: "consumer"` with three `null` dimensions, and `check_print_basis` refuses a producer-stamped `printable` or a foreign envelope owner (rule 3) | `ba14b32`, `1cf5cb6` |
| 2.2 | Injection points: build direction, threshold and reference point are declared **in the artifact's own model coordinate system**, and the handoff does **not** re-orient; every direction-derived reading carries the basis it was taken at. | implemented here, peer informed | `print{build_direction [0,0,1], threshold_deg 45.0, reference_point origin, basis: "… not re-oriented by this handoff"}`; `parts[].mesh.at{build_direction, threshold_deg, reference_point, covers}` — present even when the readings are `null` | `ba14b32` |
| 2.3 | `minWallMm` is `unknown` (**not** `visual`) and `unknown` **must carry a reason**; a reading an analyzer does compute is `heuristic`, never `visual`. The two axes are "not computed here" vs "a picture a human must read". | MeshQ (179 §4.1) | `gradeTiers{unknown: [minWallMm …], unknownMustCarryReason: true, futureThicknessGrade: "heuristic"}` | `b49feb1` |
| 2.4 | Bed-contact area is a **reading**; `centerOfMassStable` is a **verdict** — so the criterion is published and a bare `stable: true` is not. | MeshQ (179 §4.2) | draft §6 records the answer; the artifact publishes `bedContactAreaMm2` as a reading and no stability flag | `6415b50`, `b49feb1` |
| 2.5 | The interface is only a boundary if the consumer can **say no**: rules 1–5, the **absent-field** half, the **type** half, and the threshold's **range** (`0 < threshold_deg <= 180`, outside which an overhang reading has no meaning) are all enforced. | MeshQ (182 → `59e63fb`; 187 → `f8ccb58`; 189 → `2e9b9d9`) | `check_print_basis(real 70-piece manifest)` → `ok: True`, 0 refusals; delete `orientation` → 70 refusals; `applicable: 0` → 70 refusals; `0`/`181`/`1e9`/`-45` threshold → refused, `0.001`/`45`/`90`/`180` accepted; wrong direction → rule 5; 14 tests | `1cf5cb6`, `59e63fb`, `f8ccb58`, `2e9b9d9` |

## ③ Upper-layer shared contract — fields, schema ownership, router

| # | Conclusion | Agreed by | Evidence (command → observed) | Landed |
|---|---|---|---|---|
| 3.1 | Field ownership is per plane and written down field by field; there is exactly **one mapping** between the rule's quantity names and the artifact's field names. | CadQ (§8 mapping row), MeshQ (consistent) | draft §9.4 ownership table; §6 closed name-set conformance; `PIECE_FIELD = {brepVolumeMm3: ("brep","volume_mm3"), …}` | `-` (draft), `3ea963e` (code) |
| 3.2 | **No router between the planes.** A hop must buy a capability or it is deleted; a router would become a second owner of state that must have one owner; three named conditions would change the position. | proposed (peer review pending — 178 delivered, unacknowledged) | draft §9.1–§9.3, with the in-repo precedent (`browser_invoke_discovered` demoted because it "adds a hop and no capability") | `6415b50` |
| 3.3 | Refusal rules 1–18, each with the incident that produced it. | implemented here, peer informed | draft §5; rule 18 (an absent field must be as loud as a false one) came from ten adversarial variants: six blocked, four passed silently | `59e63fb`, `f8ccb58` |
| 3.4 | The consumer side of identity is implemented: units first, tolerance from the manifest, rule before digest, per-piece maximum with the worst piece, bounds only inside the declared family. | implemented here, peer informed | `check_identity_against(real 70-piece)` → `ok: True`, 70/70 compared, 0 outside, vintage echoed; every volume × 1.001 → 70 outside with the worst piece named | `3ea963e` |

## ④ Modelling collaboration — the practices, each paid for

| # | Conclusion | Agreed by | Evidence (command → observed) | Landed |
|---|---|---|---|---|
| 4.1 | Fifteen practices are recorded, each with the incident that produced it (refusal rules as interface, rule before digest, absent-field and wrong-type fixtures, declared precision, byte-referee). | practised by all three; recorded here | draft §10; practices 14/15 came from MeshQ 182/187 against this repository's own guard | `ce5b427`, `59e63fb`, `f8ccb58` |
| 4.2 | **Delivery is judged by the receipt tool, not by a `send` return value** — and not by your own ledger either. | practised by all three; this plane corrected its own claims | `mail-delivery-receipt.sh --message-id 169` → `found… 1/1`; four earlier receipts read `0/1` when this plane's own ledger said acknowledged, and were re-acked | `1910acb` |
| 4.3 | A numeric dispute is settled by a **third reader**, and an unclean probe is discarded rather than promoted. | MeshQ (179, 187) | MeshQ recomputed the readings from the bytes (per-triangle double + `math.fsum`) and used its own result as referee; it discarded its NaN probe as unclean (one reused list object → CPython identity fast path) | `b49feb1`, `f8ccb58` |
| 4.6 | Practice 16 is applied to this repository's own guards, not only written down: both consumer guards return dictionaries, so a maintained tool (`dev/tools/check_handoff.py`) runs them over a peer's manifest and **closes the exit code** (0 pass / 1 refusal / 2 unreadable), and the tests measure the **process**, not the return value. | implemented here | real 70-piece handoff → exit 0 and it says `not_provided` rather than agreement; threshold 181 → exit 1 with 141 refusals; deleted `orientation` → 70 refusals; stripped vintage → 1; missing file → 2; 8 subprocess tests | `dev/tools/check_handoff.py`, `dev/tests/test_check_handoff_tool.py` |
| 4.5 | **Failures must close, and every entry point must close them**: a judgement computed in one place and dropped in another reads as a green light. The shape to name is "one judgement, two call sites, one copy missing"; the guard is one implementation with several callers plus a test per entry point. | MeshQ (189 §3, measured on its own tool: `run` exits 0 while the record it returns says `pass: false`, `inspect` exits 1) | contract §8 section "Failures must close"; practice 16; this repository's self-audit: the docs-index digest is checked by `verify_docs.py` **and** `test_docs_index_digests.py` but both call the single `onshape_docs/query/source_digest.text_sha256`, and both failed together on one stale digest the same day | `2e9b9d9` |
| 4.4 | A **reproduction is not a landing**. A peer's pre-change output is recorded as reproduction, with the exact key set that shows the gap, until that peer lands its own change. | MeshQ requested this wording (185 §3) | `onshape_docs/verification/interop-overhang-faceoff-2026-10-03.md`, section "Rule 16 reproduced on a second plane — BEFORE it was landed there" | `b04224a` |

---

## Current numbers (reproduce with the commands in the rows above)

| Quantity | Value | How |
|---|---|---|
| Offline test suite | **1397 tests, OK** | `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=temp/browser-common-site .venv/bin/python -m unittest discover -s dev/tests` |
| Documentation verification | **17/17 checks passed** | `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python onshape_docs/verification/verify_docs.py` |
| Registered tools | **116** | `len(mcp_main.win.mcp.server.TOOLS)` |
| Real Onshape REST calls this negotiation | **0** | `LIVE_API_ENABLED` never set; every leg above runs offline or through the browser |
| Set signature of the 70-piece handoff | `7f4271064f1107bebb3aaaf40944b2690285b4aed8c6a7c55ceee54728608292` | unchanged across the print-block, tolerance and vintage additions (measured, not assumed) |
| Byte identity of the two producers' STLs | **70/70 byte-identical** | four-way join (`/tmp/join_cadq.py`) |

## Not concluded (kept visible so it cannot be mistaken for settled)

| Open item | Who owes it | State |
|---|---|---|
| Import leg live verification I1–I6 | a human with a signed-in browser | tool + ledger ready; `I6` is offline-provable first; **the only remaining structural gap on this plane** |
| MeshQ's printing-precision alignment + `applicable` reason | MeshQ | "our item 17", awaiting its owner's word; it declined to fake a receipt |
| Rule 16 paired output (post-landing) | MeshQ | reproduction recorded; the paired comparison waits for its change |
| `run` mapping its own rule verdicts into the exit code / MCP outcome | MeshQ | found and root-caused by MeshQ (its item 18); this plane recorded the general rule (practice 16) and will record its raw output as a second-plane reproduction **when it lands** |
| The two offending CadQ fields (mesh-family `bounds_mm`, mesh volume vs the bytes) | CadQ | reported with numbers (54/70 bounds, 2.41e-6 volume); unacknowledged as of this record |
| §9 router position, and interference readings as a print input | CadQ | delivered in 178/181/184; no answer yet |
