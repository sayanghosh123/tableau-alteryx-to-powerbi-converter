# Validation methodology

The proof suite uses layered validation. Automated tests verify that known patterns are parsed and translated into documented scaffolds. Human review remains required for semantic parity.

| Layer | What is checked | Mechanism | Pass criteria |
| --- | --- | --- | --- |
| Parser validation | Synthetic `.twb` and `.yxmd` XML can be read | Unit tests materialize catalog entries | No parse failures |
| Artifact validation | Expected TMDL, Power Query M, and HTML report files exist | CLI scenario runs | All expected files are generated |
| Structural validation | Generated code has balanced delimiters and no stale placeholders | Unit assertions | No `prev_step`, no unresolved path placeholder, balanced braces |
| Pattern validation | Known translations emit documented markers | Scenario token checks | Expected DAX/M fragments are present |
| Public-safety validation | Checked-in and generated text is free from restricted identifiers | Denylist assertions and grep scans | No matches |
| Semantic validation | Output values and report behavior match source intent | Manual review with representative data | Reviewer sign-off |

## Test inventory

| Test | Scope | Why it matters |
| --- | --- | --- |
| `test_sample_migration_generates_structural_outputs` | Quick-start example | Ensures the README path remains functional |
| `test_scenario_catalog_has_expected_coverage` | Catalog breadth | Confirms 20 Tableau and 20 Alteryx scenarios remain present |
| `test_twenty_by_twenty_scenario_matrix` | End-to-end scenario suite | Runs each paired scenario through the CLI and asserts output markers |
| `test_checked_in_text_is_free_from_restricted_terms` | Public release safety | Prevents restricted identifiers from re-entering the repo |

## How to interpret results

Passing tests prove that the converter handles the documented synthetic patterns structurally and consistently. They do not prove that an arbitrary source asset will migrate without review. Medium-confidence outputs are expected in the suite because they represent realistic migration areas where an accelerator should assist while preserving a clear review flag.
