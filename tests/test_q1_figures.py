"""Check evidence coupling at the plotting boundary."""
import copy
import json
from pathlib import Path
import unittest

from scripts.run_q1_figures import validate_report


class FigureEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).resolve().parents[1] / "analysis/q1_tables/tables.json"
        cls.reports = json.loads(source.read_text())["reports"]

    def test_existing_evidence_validates(self):
        for report in self.reports.values():
            model, price = validate_report(report)
            self.assertEqual(model.horizon, 144)
            self.assertEqual(len(price), 144)

    def test_altered_table_is_rejected(self):
        r = copy.deepcopy(next(iter(self.reports.values())))
        r["tables"]["optimized"]["daily_totals"]["cost_yuan"] += 1
        with self.assertRaisesRegex(ValueError, "Table/schedule mismatch"):
            validate_report(r)

    def test_altered_schedule_is_rejected(self):
        r = copy.deepcopy(next(iter(self.reports.values())))
        r["comparison"]["strategies"]["optimized"]["schedule"]["G"][0] += 1
        with self.assertRaisesRegex(ValueError, "physical validation"):
            validate_report(r)

    def test_real_input_cannot_be_labeled_synthetic(self):
        r = copy.deepcopy(next(iter(self.reports.values())))
        r["input"]["input_metadata"]["input_kind"] = "standardized"
        with self.assertRaisesRegex(ValueError, "synthetic evidence only"):
            validate_report(r)
