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

## The twelve rules

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

## Negative samples: admission vs unit test

Two classes are deliberately kept apart (interface decision §6.1):

* **admission** = the real incident in `measured_basis` (a plane other than the rule's
  author measured it, or the author's own recorded failure);
* **unit test** = the generated `fixtures/bad__R*__*.json`, which the author wrote to
  exercise *this* code. They are never evidence.

`dev/tools/build_verification_fixtures.py` generates one good slice and one bad sample per
rule (R7 and R8 have two), plus `expected_verdicts.json`:

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
12/12 rules and its projection machine-checks.

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
