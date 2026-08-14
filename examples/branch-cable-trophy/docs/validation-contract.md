# Validation contract

The detailed default validation run must satisfy all of the following:

- Feature Studio exposes `branchCableTrophyDisplay`.
- Part Studio custom feature state is `OK`.
- Part count is exactly 132:
  - 1 base
  - 1 plaque insert
  - 12 root collars
  - 84 strands
  - 17 corner connectors
  - 17 terminals
- Required name prefixes exist:
  - `base`
  - `plaqueInsert_blank`
  - `rootCollars_`
  - `blackStrands_`
  - `yellowStrands_`
  - `cornerConnectors_`
  - `terminals_`
- Bounds are approximately:
  - X: within ±65 mm
  - Y: within ±45 mm
  - Z: 0–115 mm
- Five preview views render as non-empty PNGs.

The validation script raises a nonzero exit status when a required invariant fails.

## Simplified-mode smoke test

With `detailedStrands=false`, retain:

- 17 cable sweeps
- 17 corner connectors
- 17 terminals
- the same base, plaque, and 12 roots

Expected simplified part count: 65. This mode was instantiated through the API and regenerated with status `OK`; the observed part count was 65.
