# Confidence ratings

Confidence ratings describe how complete the generated scaffold is for a known migration pattern. They do not indicate validated business parity.

| Rating | Meaning | Typical output | Required validation |
| --- | --- | --- | --- |
| High | Pattern is explicitly parsed and mapped deterministically | Review-ready DAX or M scaffold | Compare representative output values |
| Medium | Pattern is scaffolded but semantics may vary | Review flag in report | Inspect grain, ordering, joins, and edge cases |
| Low | Pattern is discovered but cannot be safely translated | Placeholder or pass-through scaffold | Manual rewrite is likely |

## What raises confidence

- Explicit formula metadata
- Single-branch workflow shape
- Standard aggregate, filter, sort, select, and projection operations
- Clear field names and typed source columns

## What lowers confidence

- Branch fan-in/fan-out that requires graph-aware lineage
- Row-order dependent logic without explicit sort or partition metadata
- LOD and table calculations that depend on visual grain
- Regex, append-fields, joins, unions, and reshaping that require semantic decisions
- Source bindings, credentials, and deployment settings

## Reporting principle

The converter should fail loudly and label uncertainty. Medium and low confidence entries must remain visible in the HTML report so reviewers know where manual validation is required.
