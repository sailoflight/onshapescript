"""The refusal rules of the three-plane verification-report contract (v1).

The rule table is **data, not prose**. Every row names the rule, the evidence layer it
belongs to, the fixture that exercises it, and the **measured** incident it rests on.

Two classes of negative sample are deliberately kept apart (interface decision §6.1,
agreed with the coordinator on 2026-10-04):

* ``measured_basis`` -- a **real incident**, naming **which plane measured it**. This is
  what makes a rule admissible: the author's own imagination is not admission.
* ``negative_control`` -- a mutation the author wrote to test *this* code. It is a unit
  test, not admission, and it must never be laundered into the contract as evidence.

House conventions (same as ``dev/tools/check_handoff.py``): a refusal is a dict with
``rule``, ``where``, ``problem``, ``required_fix``; exit 0 = passed and every rule ran,
1 = a refusal **or** a rule that did not run, 2 = the input could not be read.
"""

from __future__ import annotations

REQUIRED_TOP_LEVEL = (
    "schema",
    "producer",
    "artifact",
    "claims",
    "complete",
    "tolerances",
    "vintage",
    "cost",
)

#: The shape a report must declare, agreed by the three planes.
SCHEMA_ID = "geometry-verification/verification-report"
SCHEMA_VERSION = 1

#: A digest that does not survive a re-write must say so and say what that costs.
UNSTABLE_DIGEST = "sha256_stable_evidence"

#: The canonical form of an explicit absence, measured on MeshQ's real artifact (mail 290):
#: the `value` key is always present, and a `null` value must carry its own reason. A missing
#: field and a declared absence must never look alike.
NULL_REASON_KEY = "null_reason"

RULES: list[dict] = [
    {
        "id": "R1",
        "title": "Unknown or absent schema id / version",
        "layer": "geometry",
        "needs": ("schema",),
        "negative_control": "bad__R1__unknown_schema_version.json",
        "measured_basis": (
            "This plane's own EWF instance declared schema version 0.6.0 while the eight schema "
            "files said 0.6.1; the consumer tool raised RuntimeError instead of judging, i.e. an "
            "unknown shape has to be *refusable*, not a crash and not a silent coercion "
            "(onshapescript, dev/tests/test_ewf_instance.py)."
        ),
    },
    {
        "id": "R2",
        "title": "No producer revision to attribute the report to",
        "layer": "geometry",
        "needs": ("producer",),
        "negative_control": "bad__R2__no_revision.json",
        "measured_basis": (
            "The mailbox interop review (agent-infra, 2026-09-30) found external verification "
            "receipts that did not name the revision they verified, so a 'run it verbatim' claim "
            "could not be reproduced once the document moved (coordinator's D21 3b)."
        ),
    },
    {
        "id": "R3",
        "title": "Digest missing, malformed, or unstable without reason and consequence",
        "layer": "geometry",
        "needs": ("artifact",),
        "negative_control": "bad__R3__unstable_digest_without_reason.json",
        "measured_basis": (
            "This plane measured that a STEP export changes bytes on every write (the header "
            "carries timestamps), so a hash addresses *this delivery*, not the geometry; two "
            "producers' ang0.1 STLs were byte-identical 70/70 while the STEP legs were not "
            "(onshapescript, ledger 1.5)."
        ),
    },
    {
        "id": "R4",
        "title": "Units undeclared",
        "layer": "geometry",
        "needs": ("artifact",),
        "negative_control": "bad__R4__no_units.json",
        "measured_basis": (
            "A wrong unit declaration round-trips with 0.0 % error, because the checker compares "
            "the number the sender wrote against the number the sender wrote (onshapescript, "
            "handoff draft 1)."
        ),
    },
    {
        "id": "R5",
        "title": "A tolerance with no owner, or no vintage",
        "layer": "geometry",
        "needs": ("tolerances", "vintage"),
        "negative_control": "bad__R5__tolerance_without_owner.json",
        "measured_basis": (
            "MeshQ's own `inspect --expect-volume` defaulted to max(0.01 mm^3, 1e-4*|X|) = 0.01 %% "
            "while curved-mesh error reaches 1.2 %, and its CLI had no `--volume-tolerance`, so the "
            "caller had nowhere to declare the tolerance it accepts (MeshQ mail 267, its open item "
            "24) -- a tolerance without an owner is an undeclared assumption."
        ),
    },
    {
        "id": "R6",
        "title": "A reading with no family, no algorithm, or no achieved precision",
        "layer": "geometry",
        "needs": ("readings",),
        "negative_control": "bad__R6__reading_without_achieved.json",
        "measured_basis": (
            "MeshQ measured the same word 'volume' at -1.226 % (tessellation 48/24) and -18.68 % "
            "(12/6) against the analytic 654.498 mm^3, while the bounding box stayed exact "
            "(MeshQ mail 267) -- without family/algorithm/achieved the two numbers are incomparable."
        ),
    },
    {
        "id": "R7",
        "title": "Bounds family unreadable under either name, or two names that disagree",
        "layer": "geometry",
        "needs": ("readings",),
        "negative_control": "bad__R7__two_names_disagree.json",
        "measured_basis": (
            "One field carried two names (bounds_mm vs tessellation.bounds_mm) and the *same* name "
            "carried four implementations with four different answers; a checker must read both "
            "names and refuse a contradiction rather than pick one (onshapescript, ledger 1.11)."
        ),
    },
    {
        "id": "R8",
        "title": "Image without its basis, or a structural claim with no image",
        "layer": "morphology",
        "needs": ("evidence",),
        "negative_control": "bad__R8__image_without_basis.json",
        "measured_basis": (
            "CadQ rendered a 70-solid cabinet whose six numeric acceptances were all green while "
            "the drawers had been cut into a plate and a thin rod (CadQ mail 235); separately this "
            "plane's import verdict once credited an internal `CAD 导入` bookkeeping row as the "
            "landed geometry (onshapescript, 2026-10-03) -- a rendered view falsifies structure "
            "that numbers under-determine."
        ),
    },
    {
        "id": "R9",
        "title": "A bare verdict field somewhere in the report",
        "layer": "topology",
        "needs": ("claims",),
        "negative_control": "bad__R9__bare_verdict_field.json",
        "measured_basis": (
            "This plane's print-fit draft publishes `centerOfMassStable`-shaped fields; the rule "
            "adopted for the contract is to publish the *reading plus the criterion plus its "
            "owner*, never `stable: true`, because a bare judgement cannot be re-checked while a "
            "reading can (onshapescript, print-fit draft open question 2)."
        ),
    },
    {
        "id": "R10",
        "title": "A declared criterion that was never evaluated looks like a pass",
        "layer": "geometry",
        "needs": ("complete", "not_evaluated"),
        "negative_control": "bad__R10__incomplete_looks_green.json",
        "measured_basis": (
            "MeshQ's wording, adopted verbatim: a declared criterion that was not evaluated looks "
            "exactly like a passing one; its `complete` + per-criterion `not_evaluated` is the "
            "executable form (MeshQ, relayed by the coordinator in mail 260)."
        ),
    },
    {
        "id": "R11",
        "title": "Two outputs of the same code offered as evidence",
        "layer": "topology",
        "needs": ("independence",),
        "negative_control": "bad__R11__same_code_as_evidence.json",
        "measured_basis": (
            "This plane's `outwardOriented` is `signed_volume > 0` -- one computation wearing two "
            "names; MeshQ reports the same inside its own plane (its `volume` closure test and its "
            "`deviation` selector share `face_distances`). Only the three-plane recomputation of "
            "the same 70 STL byte sets is `different_kernel`: onshapescript 9.8e-13 / CadQ "
            "4.99e-07 / MeshQ 3.39e-06 relative deviation (MeshQ mail 270)."
        ),
    },
    {
        "id": "R12",
        "title": "A CSV projection that was not machine-checked against the report",
        "layer": "geometry",
        "needs": ("csv_projection",),
        "negative_control": "bad__R12__projection_unchecked.json",
        "measured_basis": (
            "This plane's EWF instance keeps a README projection of its YAML source; the projection "
            "drifted until a machine check was added (the guard test now compares generated bytes "
            "against the file on disk) -- two shells of one dataset always drift "
            "(onshapescript, dev/tests/test_ewf_instance.py)."
        ),
    },
]

RULE_IDS: list[str] = [rule["id"] for rule in RULES]

#: Keys that must not appear anywhere: a bare judgement cannot be re-checked.
BARE_VERDICT_KEYS = ("stable", "printable", "ok", "pass", "verdict")

#: The only independence level that is real geometric evidence from another kernel.
INDEPENDENCE_LEVELS = ("different_kernel", "different_implementation_same_kernel", "same_code")

#: The five items an image must carry, or it is 'not measured' rather than 'passed'.
IMAGE_BASIS_KEYS = ("views", "fit", "source_sha256", "recipe_version", "parts_drawn")

#: Bounds may be declared under either name; both are read, a disagreement is refused.
BOUNDS_FAMILY_KEYS = ("bounds_family", "boundsAlgorithm")

#: The family this plane publishes for a bounds read off the artifact bytes.
COMPARABLE_BOUNDS_FAMILY = "tessellation_vertices(artifact_bytes)"

#: Layers whose presence together makes a claim structural (and therefore image-hungry).
STRUCTURAL_LAYERS = ("geometry", "topology")
