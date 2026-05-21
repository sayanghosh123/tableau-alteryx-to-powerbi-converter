# Tableau and Alteryx to Power BI Converter

An offline-first migration accelerator that inspects Tableau workbook XML (`.twb`) and Alteryx workflow XML (`.yxmd`), then generates draft Power BI migration artifacts for engineering review:

- Power BI semantic model scaffolds in TMDL
- Power Query M dataflow scaffolds
- An HTML review report with inventory, confidence, and follow-up notes

The converter is designed to reduce discovery and first-pass translation effort. It does **not** claim one-click parity with existing Tableau dashboards or Alteryx workflows; generated artifacts require validation before production use.

## Proof suite

The repo includes a deterministic synthetic proof suite covering **20 Tableau report scenarios** and **20 Alteryx workflow scenarios**. The suite is designed to show what the accelerator handles, where it creates review-ready scaffolds, and where human validation remains required.

| Evidence | Scope |
| --- | --- |
| `scenario_suite.py` | Catalog of 40 domain-neutral synthetic scenarios |
| `examples/source/tableau` and `examples/source/alteryx` | Checked-in generated fixtures for all 40 scenarios |
| `tests/test_migrate.py` | End-to-end tests that run every paired Tableau/Alteryx scenario through the CLI |
| `docs/scenario-coverage.md` | Scenario-by-scenario coverage matrix |
| `docs/confidence-ratings.md` | Confidence rubric and review expectations |
| `docs/known-limitations.md` | Explicit boundaries to avoid overpromising |
| `docs/validation-methodology.md` | What automated checks prove and what still needs human review |

## Repository layout

```text
.
├── examples/
│   └── source/
│       ├── tableau/              # 20 checked-in synthetic Tableau scenario workbooks
│       ├── alteryx/              # 20 checked-in synthetic Alteryx scenario workflows
│       ├── sales_analytics.twb   # Synthetic Tableau workbook sample
│       └── order_prep.yxmd       # Synthetic Alteryx workflow sample
├── docs/                         # Coverage, confidence, validation, and limitation notes
├── scripts/
│   └── generate_scenarios.py      # Optional materializer for the synthetic scenario catalog
├── tests/
│   └── test_migrate.py           # Smoke and structural regression tests
├── scenario_suite.py              # 20 Tableau + 20 Alteryx synthetic scenario definitions
├── migrate.py                    # Main converter CLI
├── requirements.txt              # Optional LLM dependency notes
└── README.md
```

Generated `migrated/` and `reports/` folders are intentionally ignored by Git so private source metadata is not accidentally committed.

## Quick start

Prerequisite: Python 3.10 or later.

```bash
python migrate.py \
  --tableau examples/source/sales_analytics.twb \
  --alteryx examples/source/order_prep.yxmd \
  --output migrated \
  --reports-dir reports
```

On Windows PowerShell:

```powershell
python .\migrate.py `
  --tableau .\examples\source\sales_analytics.twb `
  --alteryx .\examples\source\order_prep.yxmd `
  --output .\migrated `
  --reports-dir .\reports
```

After the run:

```text
migrated/
├── dataflows/
│   └── order_prep.pq
└── power_bi/
    └── definition/
        ├── model.tmdl
        └── tables/
            ├── _Measures.tmdl
            └── Sales.tmdl

reports/
└── migration_report.html
```

## What it translates

### Tableau to DAX/TMDL

| Tableau pattern | Draft DAX pattern | Typical confidence |
| --- | --- | --- |
| `SUM`, `AVG`, `COUNT`, `COUNTD`, `MIN`, `MAX` | Native DAX aggregations | High |
| `{ FIXED [dimension] : SUM(...) }` | `CALCULATE(..., ALLEXCEPT(...))` | High |
| `{ INCLUDE/EXCLUDE ... }` | `CALCULATE` scaffold with grain review flag | Medium |
| `RUNNING_SUM(...)` | `CALCULATE` plus `FILTER(ALLSELECTED(...))` | High |
| `LOOKUP(..., offset)` | `CALCULATE` plus `DATEADD` scaffold | Medium |
| `IF/ELSEIF/ELSE` and `CASE WHEN` | `IF` and `SWITCH(TRUE())` | Medium to high |

### Alteryx to Power Query M

| Alteryx tool | Draft Power Query M output | Notes |
| --- | --- | --- |
| Input | `Csv.Document` plus promoted headers | Replace source binding |
| Filter | `Table.SelectRows` | Basic expression translation |
| Formula | `Table.AddColumn` chain | Review data types |
| Multi-Row Formula | Indexed running calculation scaffold | Review row order and partitioning |
| Summarize | `Table.Group` | Uses parsed group and aggregation metadata when present |
| Sort | `Table.Sort` | Uses parsed sort metadata when present |
| Select | `Table.SelectColumns` | Uses parsed selected fields when present |
| Join / Union | Review-ready scaffold | Requires wiring exact upstream branches |

## Optional LLM assistance

The default path is deterministic and uses only the Python standard library. For low-confidence expressions, you can optionally enable an OpenAI-compatible provider:

```bash
GITHUB_TOKEN=<token> python migrate.py \
  --tableau examples/source/sales_analytics.twb \
  --alteryx examples/source/order_prep.yxmd \
  --llm-provider github
```

Supported providers are `azure`, `openai`, `github`, and `custom`. Install the optional SDK first if you use this mode:

```bash
pip install openai
```

## Validation workflow

Run the included checks:

```bash
python -m unittest discover -s tests -v
```

The tests compile the CLI, run the sample migration, run 20 paired Tableau/Alteryx scenario cases into temporary folders, and check that generated TMDL/M/report artifacts are structurally coherent and free from restricted sample identifiers.

The generated synthetic scenario inputs are checked in under `examples/source/tableau` and `examples/source/alteryx`. To regenerate them locally from the catalog:

```bash
python scripts/generate_scenarios.py --output examples/source
```

See `docs/using-the-suite.md` for details.

For a real migration, validate at least:

1. Source bindings and credentials
2. DAX filter context and relationship behavior
3. Power Query data types and query folding
4. Multi-row, join, union, and branch semantics
5. Visual-level parity against representative reports
6. Security, privacy, and deployment settings

## Privacy and publishing guardrails

- The checked-in examples are synthetic.
- Generated local outputs are ignored by default.
- Presentation files and common credential/cache files are ignored.
- Do not commit real workbook, workflow, report, or generated migration artifacts unless they have been explicitly approved for publication.
