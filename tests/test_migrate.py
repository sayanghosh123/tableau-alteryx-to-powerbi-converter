import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
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


if __name__ == "__main__":
    unittest.main()
