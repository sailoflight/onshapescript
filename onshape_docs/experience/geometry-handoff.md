# Geometry handoff between the CAD planes: what a measurement actually measures

Reusable, verified lessons from the three-plane handoff work (onshapescript / CadQ / MeshQ,
2026-09-30 → 2026-10-03). Every claim here cost a real measurement, and two of them cost a retraction
first. The contract that came out of it is `docs/roadmap/THREE_PLANE_HANDOFF_SCHEMA_DRAFT.md`; the
per-incident evidence is in `onshape_docs/verification/interop-*.md`.

## What the browser export leg declares, and what it refuses to claim

A staged browser STEP export (`output/<exportId>/step-manifest.json`) now carries a `declaration` block in
the cross-plane handoff's vocabulary (`onshapescript.handoff/0.4-draft`). It is additive: `schemaVersion`,
`artifactType`, `exportId` and `artifact` keep their meaning.

| Key | What it says |
|---|---|
| `declaration.identity.sha256` | the digest of the delivered bytes |
| `declaration.identity.sha256_stable: false` | with the reason: an ISO-10303-21 header timestamp lands in the file, so two exports of identical geometry differ byte for byte. The digest addresses **this delivery**, not the geometry |
| `declaration.identity.identity_rule` | version `onshapescript.step-artifact-identity/1`, `identityProof: false`, and the note that no kernel runs in this leg |
| `declaration.geometry.kernel` / `.measure` / `.at` / `.parts` | all `null` — this leg has no CAD kernel |
| `declaration.geometry.readsNothing` | in words: the block publishes no volume, area or bounds reading; the consumer or a measuring plane produces those |
| `declaration.geometry.solidCount` | a **text** count of `MANIFOLD_SOLID_BREP(`/`BREP_WITH_VOIDS(` entity names, graded `heuristic` (never `reliable`) with its method and its undercount risk named |
| `declaration.geometry.tessellation` | `not_produced_here`, with the reason: a tessellation declaration belongs to the plane that produces one |

Two lessons are baked in, both paid for in this negotiation. **A rule that only fires when a field is
present is not a gate**, so this block is written out rather than omitted: an absent field reads as "fine"
while a declared gap reads as a gap. And **a digest without its rule cannot be compared**, so the rule
version travels beside the number instead of being assumed.

The import leg's counterpart record (`import-manifest.json`) measures the local source with `path` **and**
`sha256`, plus `sha256Stable: false` and the same note — so a landing can be traced to the exact bytes it
came from, and nobody can mistake the digest for content identity.

## 1. "The bounding box" is not one measurement — and one library call changes which one you get

Four readers, one piece, four answers (max gap **3.19e-2 mm**, on 70/70 pieces):

| Family | Piece #0 `max` | Piece #2 `max` |
|---|---|---|
| mesh vertices (the artifact's own bytes) | `[7.0, 380.0, 86.0]` | `[220.699997, 348.0, 185.350006]` |
| exact B-Rep read **before** tessellation | `[7.0, 380.0000001, 86.0]` | `[220.7, 348.0, 185.35]` |
| exact B-Rep read **after** exporting the STL | `[7.0000001, 380.0008704, 86.0000001]` | `[220.700488, 348.0000001, 185.381891]` |

The third row is a trap, not a bug in the caller's arithmetic: **CadQuery's STL export mutates the
shape's cached bounds.** Same shape, same process, immediately before and after
`cq.exporters.export(shape, path, exportType="STL", ...)`:

```
#0  ymax 380.0000001000 -> 380.0008703904
#2  xmin   7.5000000000 ->   7.4995117079
```

So a producer that measures the box *after* exporting publishes a number in no other implementation's
family, and a self-comparison (its own two readings of its own two fields) reports "no gap" while a peer
sees 3.2e-2 mm. Rules that follow, and are now enforced in the producer:

* a bounding-box field declares its **algorithm** (`boundsAlgorithm`), and the comparable family — mesh
  vertices, reproducible from the artifact bytes — is the one that travels;
* a difference **within** one family is a defect signal (measured `0.0` across two full tessellation runs
  on all 70 pieces); a difference **across** families is a *method* gap (a chord lies inside the surface
  it approximates, so up to the declared deflection is expected). Never report one as the other;
* the identity tolerance is **per quantity**: one number cannot govern a volume that agrees to 1e-9 and a
  box that differs by 3e-2 between families.

## 2. A verdict computed over a broken edge graph is vacuously true

`orientation.consistent: true` on a mesh that is **not** closed means nothing: the surviving shared
edges can each be used once in each direction while the graph is shredded. Measured on a real probe built
by getting the binary STL vertex offsets wrong (two identical vertices in one triangle):

```
watertight: false   nonManifoldEdges: 1   consistent: true
```

The check "proves nothing" and yet reports success. So a producer publishes `applicable` beside
`consistent` (with the reason), and a consumer must not read the verdict without it. The sibling fixture
with a **real** flipped winding shows the contrasting, meaningful case: `watertight: true`,
`consistent: false`, `inconsistentEdgePairs: 3`, `inconsistentFaceIndices: [0, 5, 61, 775]` — and the
area is unchanged (`464.320189554 mm²`, exactly equal to the clean piece) while the signed volume and
every direction-derived reading go `null` with `applicable: false`.

**Corollary for fixtures:** welding is the difference between a check and a ritual. A per-triangle reader
that does not weld by position sees a shredded edge graph on any face-seamed mesh and will happily report
"no inconsistent pairs"; state the welding tolerance and publish the denominator (`checkedEdges`, which
for a closed cube is exactly `3 · triangles / 2`).

## 3. Report the per-piece maximum, not the aggregate

In one 70-piece batch, two implementations of the same policy agreed to **1.31e-7** in the aggregate while
their worst per-piece disagreement was **3.39e-6** — a factor of 26, hidden by the sum, because errors of
opposite sign cancel. A cross-plane claim states the per-piece maximum and the worst piece's index.

## 4. A digest is a fast path in both directions, and only that

* a **differing** digest is not proof of different geometry (a STEP file carries a header GUID and a
  timestamp: two exports of one shape differ by 34 bytes; two producers' STL bytes here did *not* differ,
  but that is a property of one writer, not of digests);
* an **equal** digest is not proof of identical geometry either;
* and a digest taken over readings must be taken over readings from **one declared family**: a set
  signature that mixed an exact box with a mesh box would change whenever the producer's measurement order
  changed — which is exactly what happened here before the families were separated.

## 5. A declaration and an acceptance gate are different things

`matches_declaration: true` means "the producer used what was declared", not "the result passes the
consumer's gate". Measured on the real fixture: declaring/using 0.3 rad gives a 0.103 % volume error
(fails a 0.05 % gate; 12 of 70 pieces), 0.1 rad gives 0.012 % (passes), and tightening the *linear*
tolerance 2.5× (0.05 → 0.02 mm) changes nothing while 32× (0.05 → 0.0016 mm) does. So the angular
component is the binding one here — and that sentence is only true **relative to the factor measured**,
which is why a binding claim must ship with the measurement that decided it and never be hand-asserted.
