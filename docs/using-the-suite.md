# Using the scenario suite

## Run all checks

```bash
python -m unittest discover -s tests -v
```

The full test run materializes synthetic XML into temporary folders, runs the converter, and checks generated TMDL, Power Query M, and HTML reports.

## Generate inspectable fixtures

To write the 20 Tableau and 20 Alteryx synthetic inputs to disk:

```bash
python scripts/generate_scenarios.py --output generated_scenarios
```

`generated_scenarios/` is ignored by Git. Use it for local inspection, demos, or targeted converter debugging.

## Run one generated pair manually

```bash
python migrate.py \
  --tableau generated_scenarios/tableau/tbl-01_aggregate_arithmetic.twb \
  --alteryx generated_scenarios/alteryx/alx-01_linear_cleanse_aggregate.yxmd \
  --output migrated \
  --reports-dir reports
```

## Add a new scenario

1. Add a `TableauScenario` or `AlteryxScenario` entry in `scenario_suite.py`.
2. Include a short purpose, expected output tokens, confidence rating, and review focus.
3. Run `python -m unittest discover -s tests -v`.
4. Update `docs/scenario-coverage.md` if the public coverage matrix changes.

## Scenario authoring guidance

| Field | Required | Guidance |
| --- | --- | --- |
| Scenario ID | Yes | Use `TBL-##` or `ALX-##` |
| Name | Yes | Keep it generic and domain-neutral |
| Purpose | Yes | State the migration pattern being exercised |
| Expected tokens | Yes | Use stable DAX/M markers, not whole-file snapshots |
| Confidence | Yes | Use the rubric in `docs/confidence-ratings.md` |
| Review focus | Yes | Explain what a human reviewer must still validate |
