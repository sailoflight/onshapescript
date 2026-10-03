# Three-plane verification-report contract — this plane's reference implementation (v1)

Three independent modeling planes (`onshapescript`, `CadQ`, `MeshQ`) agreed on one
**verification report** shape, so that a delivery can be reconciled by a plane other than
the one that produced it. This package is this plane's reference implementation of that
contract. It is stdlib-only and never touches the network.

The decision it implements lives in
[`docs/roadmap/THREE_PLANE_VERIFICATION_INTERFACE_V1.md`](../../docs/roadmap/THREE_PLANE_VERIFICATION_INTERFACE_V1.md)
(v1.2, with every change of mind recorded in its header); the running reconciliation ledger
is [`docs/roadmap/THREE_PLANE_NEGOTIATION_LEDGER.md`](../../docs/roadmap/THREE_PLANE_NEGOTIATION_LEDGER.md).

## The three files that matter

| File | Role |
|---|---|
| `schema/verification_report_v1.schema.json` | the **declarative** half: the shape a report must have |
| `runner.py` | the **normative** half: judgement, refusals, exit codes. **The runner is the only authority.** |
| `adapters.py` | **extraction only**: pull fields out of an artifact (our manifest, MeshQ's probe result). An adapter never judges. |
| `slices.py` | assemble a report from extracted fields + machine-check its own CSV projection. Assembly is not judgement. |

Refusal semantics cannot be expressed in JSON Schema (a disagreement between two names is
not a shape error, an unevaluated criterion looks like a pass, a bare verdict is a shape
that *should* be refused), which is why the runner is the authority and the schema is a
consumer's convenience.

Exit codes follow the house convention of `dev/tools/check_handoff.py`:

```
0  everything checked passed and every rule ran
1  a refusal, or a rule that did not run   (an unevaluated rule is as loud as a refusal)
2  the input could not be read
```

## The 13 rules (all binding since 2026-10-04)

`rules.py::RULES` is the rule table **as data**: id, evidence layer, the fixture that
exercises it, and **`measured_basis` — the real incident the rule rests on, naming which
plane measured it.** A rule whose basis is the author's imagination is not admissible.

R1 unknown schema version · R2 no revision · R3 unstable digest without reason/consequence ·
R4 units undeclared · R5 a tolerance with no owner, or no vintage · R6 a reading with no
family/algorithm/achieved · R7 a bounds family unreadable under **either** of its two names,
or two names that disagree (a contradiction, never a coin flip) · R8 an image without its
basis, or a structural claim with no image · R9 a bare verdict field · R10 a declared
criterion that was never evaluated looking like a pass · R11 two outputs of the same code
offered as evidence · R12 a CSV projection that was not machine-checked against the report.

**R13 (binding since 2026-10-04): per-shell self-consistency offered as whole-part validity.** MeshQ
measured `recalc_normals` flipping the winding of an internal cavity in a multi-shell part — volume
22274.898 (−0.688 %) → 25725.102 (+14.695 %) while `closed_shells` / `watertight` / `components: 2` /
`inconsistent_edge_pairs: 0` / `outward_normals: true` were **all identical**. The coordinator judged the
rule admissible but required the plane that measured it to confirm that it applies to this interface
(mail 298 §3); MeshQ did exactly that in one line (mail 305, "R13: 可以绑定", signed
`MeshQ/RoseStork 实测`) and this plane then **reproduced the evidence itself** before binding it
(`artifacts/contract-slice/work{,_no_recalc,_no_merge,_neither}/meshq_result.json`: signed volume
22274.898343 → 25725.101657 against `expected_volume_mm3` 22429.203673205102, with every
closure/orientation field identical in all four runs). `confirmed_by` / `confirmed_at` /
`reproduced_here` in the rule table record that admission.

The unconfirmed-rule machinery stays: a rule whose `status` is `proposed` refuses **nobody** yet still
prints what it *would* refuse (`proposedRefusals`), so the peers judge the impact before it starts
rejecting reports. `RuleAdmission` proves **both** directions —
`test_r13_is_binding_and_refuses_its_own_negative_control` (shipped table refuses) and
`test_the_machinery_still_protects_the_next_unconfirmed_rule` (flipped back to `proposed` in memory, it
refuses nobody and still reports the impact).

## Negative samples: admission vs unit test

Two classes are deliberately kept apart (interface decision §6.1):

* **admission** = the real incident in `measured_basis` (a plane other than the rule's
  author measured it, or the author's own recorded failure);
* **unit test** = the generated `fixtures/bad__R*__*.json`, which the author wrote to
  exercise *this* code. They are never evidence.

`dev/tools/build_verification_fixtures.py` generates one good slice and one bad sample per
rule (R7 and R8 have two) — **17 bad + 1 good** — plus `expected_verdicts.json` and, for rules that are
not binding yet, `expected_proposed.json` (their fixtures must be *accepted* while proposed; it is empty
while every rule is binding, and it is what the next unconfirmed rule would land in):

```
python dev/tools/build_verification_fixtures.py --write   # regenerate the fixtures
python dev/tools/build_verification_fixtures.py --check   # fail if disk ≠ generator
python dev/tools/build_verification_fixtures.py --facts   # rule/fixture coverage
```

Guard tests (the same admission gate, applied to this table): every rule has a negative
control that exists on disk, every rule names a measured basis **and the plane that
measured it**, and every mutation in the generator maps to a declared rule.

## The vertical slice in `fixtures/good__vertical_slice.json`

One part's worth of delivery, reconcilable end to end: per-claim readings with
`family`/`algorithm`/`achieved`, a bounds claim declared under its **second** name
(`boundsAlgorithm`), tolerances **with an owner** and a vintage, an explicitly listed
`not_evaluated` criterion, cost metadata, an independence level, and a CSV projection
declared as machine-checked. Numbers are real where they can be: the artifact digest is the
recorded signature of the real 70-piece handoff set (`7f427106…8292`) and the volumes come
from that set. The good slice carries **numeric claims only** and no image, because:

**this plane has no renderer** (`grep -rn "matplotlib\|savefig\|render_parts"
onshape_browser_mode/ mcp_main/` is empty), so the image leg is CadQ's. A numeric-only
delivery does not need an image — which is exactly the boundary the two R8 fixtures probe
from the other side (an image missing its basis; a claim that becomes structural because it
claims geometry **and** topology and ships no image).

## The slice was run on a **peer's real artifact**

`dev/verification_report/slices.py` assembles a report from extracted fields only (assembly is not
judgement) and `machine_check_projection()` performs the check R12 demands. It was pointed at
**MeshQ's own contract probe** (`/home/lijq/code/MeshQ/artifacts/contract-probe/`, read-only here),
so the reconciliation runs against a peer artifact rather than our own fixture:

```
python -m unittest dev.tests.test_verification_report_peer_slice     # 5 tests OK
```

The real result file supplies a real digest, a real **unstable** digest *with its reason* (the JSON
embeds `started_at`/`build_seconds`/`total_seconds`), the peer's declared tessellation (`segments=12`,
`rings=6`) inside the reading family, its real achieved spread (`2.827e-06` against its own limit),
and its bound family read under the **second** accepted name (`boundsAlgorithm`). The slice passes
13/13 binding rules and its projection machine-checks.

**A negative result worth keeping:** copying the peer's `inspection.verdicts.*.pass` verbatim into a
report is **refused by R9**. The adapter counts the verdicts and does not copy them: a verdict is only
re-checkable when it travels with its reading, its criterion and the owner of the criterion. Whether a
producer's verdict should travel *with* its reading is an open question for the three planes.

## The CSV projection is Excel-safe by construction

`runner.project_csv()` emits UTF-8 BOM, and guards every cell: a leading `=`/`+`/`-`/`@`
(a formula), a `9-15`-shaped date, or a 16+ digit number is prefixed with `'`.
`runner.read_projection_csv()` undoes the guard, so the projection can be **machine-checked
against the JSON** — the contract refuses a projection that declares no check (R12), because
two shells of one dataset always drift.
