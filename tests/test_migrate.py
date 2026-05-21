import ast
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scenario_suite import (  # noqa: E402
    ALTERYX_SCENARIOS,
    TABLEAU_SCENARIOS,
    write_alteryx_scenario,
    write_tableau_scenario,
)

DENYLIST = [
    "west" + "pac",
    "ap" + "ra",
    "core " + "bank" + "ing",
    "equi" + "fax",
    "sa" + "yan",
    "gh" + "osh",
    "microsoft" + ".com",
    "gh" + "osh" + "sa" + "yan",
    "one" + "drive",
]


class MigrationCliTests(unittest.TestCase):
    def test_python_310_syntax_compatibility(self):
        for path in [ROOT / "migrate.py", ROOT / "scenario_suite.py", ROOT / "scripts" / "generate_scenarios.py"]:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 10))

    def test_sample_migration_generates_structural_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            output = temp / "migrated"
            reports = temp / "reports"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "migrate.py"),
                    "--tableau",
                    str(ROOT / "examples" / "source" / "sales_analytics.twb"),
                    "--alteryx",
                    str(ROOT / "examples" / "source" / "order_prep.yxmd"),
                    "--output",
                    str(output),
                    "--reports-dir",
                    str(reports),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            measures = output / "power_bi" / "definition" / "tables" / "_Measures.tmdl"
            fact_table = output / "power_bi" / "definition" / "tables" / "Sales.tmdl"
            model = output / "power_bi" / "definition" / "model.tmdl"
            power_query = output / "dataflows" / "order_prep.pq"
            report = reports / "migration_report.html"

            for path in [measures, fact_table, model, power_query, report]:
                self.assertTrue(path.exists(), f"Missing generated file: {path}")

            measures_text = measures.read_text(encoding="utf-8")
            power_query_text = power_query.read_text(encoding="utf-8")
            report_text = report.read_text(encoding="utf-8")

            self.assertNotRegex(measures_text, r"measure '[^']+' = .+ =")
            self.assertNotIn('"Sales"', measures_text)
            self.assertIn("CALCULATE", measures_text)
            self.assertIn("DIVIDE", measures_text)
            self.assertIn("Table.Group", power_query_text)
            self.assertIn("Table.AddIndexColumn", power_query_text)
            self.assertNotIn("not [", power_query_text)
            self.assertNotIn("Row-1:", power_query_text)
            self.assertNotIn("prev_step", power_query_text)
            self.assertNotIn("[Update path]", power_query_text)
            self.assertBalanced(power_query_text, "(", ")")
            self.assertBalanced(power_query_text, "{", "}")
            self.assertIn("Generated artifacts are scaffolds", report_text)

            combined = "\n".join([measures_text, fact_table.read_text(encoding="utf-8"), power_query_text, report_text])
            for restricted in DENYLIST:
                self.assertNotIn(restricted, combined.lower())

    def test_scenario_catalog_has_expected_coverage(self):
        self.assertEqual(len(TABLEAU_SCENARIOS), 20)
        self.assertEqual(len(ALTERYX_SCENARIOS), 20)
        self.assertEqual(len({scenario.scenario_id for scenario in TABLEAU_SCENARIOS}), 20)
        self.assertEqual(len({scenario.scenario_id for scenario in ALTERYX_SCENARIOS}), 20)

        tableau_features = " ".join(
            token
            for scenario in TABLEAU_SCENARIOS
            for formula in scenario.formulas
            for token in [formula.formula]
        )
        for required in ["FIXED", "INCLUDE", "EXCLUDE", "RUNNING_SUM", "LOOKUP", "WINDOW_AVG", "WINDOW_SUM", "RANK", "COUNTD"]:
            self.assertIn(required, tableau_features)

        alteryx_types = {tool["type"] for scenario in ALTERYX_SCENARIOS for tool in scenario.tools}
        for required in {
            "Input",
            "Filter",
            "Formula",
            "MultiRowFormula",
            "Summarize",
            "Sort",
            "Select",
            "Join",
            "Union",
            "Unique",
            "Sample",
            "RecordID",
            "TextToColumns",
            "Transpose",
            "CrossTab",
            "DataCleansing",
            "Regex",
            "DateTime",
            "AppendFields",
            "Output",
        }:
            self.assertIn(required, alteryx_types)

    def test_checked_in_scenario_fixtures_are_materialized(self):
        tableau_dir = ROOT / "examples" / "source" / "tableau"
        alteryx_dir = ROOT / "examples" / "source" / "alteryx"
        self.assertEqual(len(list(tableau_dir.glob("*.twb"))), 20)
        self.assertEqual(len(list(alteryx_dir.glob("*.yxmd"))), 20)

        for scenario in TABLEAU_SCENARIOS:
            expected = tableau_dir / f"{scenario.scenario_id.lower()}_{self.slug(scenario.name)}.twb"
            self.assertTrue(expected.exists(), f"Missing Tableau fixture: {expected}")
        for scenario in ALTERYX_SCENARIOS:
            expected = alteryx_dir / f"{scenario.scenario_id.lower()}_{self.slug(scenario.name)}.yxmd"
            self.assertTrue(expected.exists(), f"Missing Alteryx fixture: {expected}")

    def test_twenty_by_twenty_scenario_matrix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            for tableau_scenario, alteryx_scenario in zip(TABLEAU_SCENARIOS, ALTERYX_SCENARIOS):
                with self.subTest(tableau=tableau_scenario.scenario_id, alteryx=alteryx_scenario.scenario_id):
                    tableau_path = temp / "source" / f"{tableau_scenario.scenario_id}.twb"
                    alteryx_path = temp / "source" / f"{alteryx_scenario.scenario_id}.yxmd"
                    output = temp / "runs" / f"{tableau_scenario.scenario_id}_{alteryx_scenario.scenario_id}" / "migrated"
                    reports = temp / "runs" / f"{tableau_scenario.scenario_id}_{alteryx_scenario.scenario_id}" / "reports"
                    write_tableau_scenario(tableau_scenario, tableau_path)
                    write_alteryx_scenario(alteryx_scenario, alteryx_path)

                    result = subprocess.run(
                        [
                            sys.executable,
                            str(ROOT / "migrate.py"),
                            "--tableau",
                            str(tableau_path),
                            "--alteryx",
                            str(alteryx_path),
                            "--output",
                            str(output),
                            "--reports-dir",
                            str(reports),
                        ],
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

                    measures_text = (output / "power_bi" / "definition" / "tables" / "_Measures.tmdl").read_text(encoding="utf-8")
                    fact_text = (output / "power_bi" / "definition" / "tables" / "Sales.tmdl").read_text(encoding="utf-8")
                    power_query_text = (output / "dataflows" / f"{alteryx_path.stem}.pq").read_text(encoding="utf-8")
                    report_text = (reports / "migration_report.html").read_text(encoding="utf-8")

                    combined_tableau = measures_text + "\n" + fact_text
                    for token in tableau_scenario.expected_tokens:
                        self.assertIn(token, combined_tableau)
                    for token in alteryx_scenario.expected_tokens:
                        self.assertIn(token, power_query_text)

                    self.assertBalanced(power_query_text, "(", ")")
                    self.assertBalanced(power_query_text, "{", "}")
                    self.assertNotIn("prev_step", power_query_text)
                    self.assertNotIn("[Update path]", power_query_text)
                    self.assertIn(tableau_scenario.formulas[0].caption, report_text)
                    self.assertIn(alteryx_scenario.tools[0]["name"], report_text)

                    generated_text = "\n".join([combined_tableau, power_query_text, report_text]).lower()
                    for restricted in DENYLIST:
                        self.assertNotIn(restricted, generated_text)

    def test_checked_in_text_is_free_from_restricted_terms(self):
        skipped_dirs = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
        skipped_suffixes = {".pyc", ".ppt", ".pptx", ".pptm", ".key", ".pem"}
        checked = []
        for path in ROOT.rglob("*"):
            if any(part in skipped_dirs for part in path.parts):
                continue
            if not path.is_file() or path.suffix.lower() in skipped_suffixes:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            checked.append(path)
            for restricted in DENYLIST:
                self.assertNotIn(restricted, text, f"{restricted!r} found in {path}")
        self.assertTrue(checked)

    def assertBalanced(self, text, left, right):
        self.assertEqual(text.count(left), text.count(right), f"Unbalanced {left}{right}")

    def slug(self, value):
        return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")


if __name__ == "__main__":
    unittest.main()
