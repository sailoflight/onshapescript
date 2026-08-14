# Feature parameters

## Primary controls

| Parameter | Default | Range | Purpose |
|---|---:|---:|---|
| Base radius | 39 mm | 32–50 mm | Cylindrical pedestal radius |
| Base height | 18 mm | 14–28 mm | Pedestal side-wall height |
| Edge fillet | 2.4 mm | 0.5–4.5 mm | Top and bottom circular-edge fillet only |
| S center Y | -2 mm | -10–10 mm | Fore/aft center of the two S rows |
| S length | 42 mm | 28–58 mm | Root-row extent along Y |
| S amplitude | 7.5 mm | 3–13 mm | S curve side displacement |
| Root row spacing | 5 mm | 2–10 mm | Separation between the two rows |
| Terminal spread | 1.22 | 0.9–1.5 | Horizontal terminal fan scale |
| Terminal height scale | 1.06 | 0.85–1.25 | Cable/terminal height scale |
| Strand radius | 0.38 mm | 0.20–0.48 mm | Individual strand radius |
| Detailed strands | true | Boolean | 4/5/6 real strands or one preview strand per bundle |

## Secondary controls

The panel also exposes plaque, terminal, root-collar, and corner-connector dimensions.

## Fixed design constraints

- 12 actual root collars.
- 17 main cable bundles.
- Shared root map: `[0,0,1,2,2,3,4,5,5,6,7,8,8,9,10,10,11]`.
- Strand counts repeat `4,5,6` across the 17 bundles.
- Exactly one blank plaque insert and 17 rectangular terminals.

## Intentional strand packing

The nominal strand-center spacing is 0.68 mm while the default diameter is 0.76 mm. This slight overlap is intentional: it makes each group read as a compact braided cable bundle and prevents large visual gaps. The bodies remain separate for appearance assignment.

## Parameter caution

Extremal combinations can cause neighboring terminals, collars, or strands to touch even though individual parameter bounds are valid. Treat the stated bounds as visual tuning ranges rather than proof that every Cartesian combination is production-safe.
