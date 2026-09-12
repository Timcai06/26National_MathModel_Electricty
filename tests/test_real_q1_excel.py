import json
from pathlib import Path
import unittest

from src.q1.excel import OUTPUT_POLICY, candidate_payload, verify_candidate

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'CUMCM2026Problems/C题/附件/附件5/result1.xlsx'


class RealExcelContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((ROOT / 'analysis/real_q1_candidate/result.json').read_text())['report']

    def payload(self, **kwargs):
        return candidate_payload(self.report, TEMPLATE, output_policy=OUTPUT_POLICY, **kwargs)

    def test_real_data_requires_explicit_opt_in(self):
        with self.assertRaises(ValueError):
            self.payload()

    def test_opt_in_does_not_accept_time_semantics(self):
        payload = self.payload(allow_real_candidate=True)
        self.assertEqual(payload['scope'], 'real-candidate-only')
        self.assertFalse(payload['semantic_acceptance'])
        self.assertEqual(len(payload['mapping']), 144)
        self.assertEqual(payload['mapping'][60]['cell'], 'B62')
        self.assertIn('T10:00:', payload['mapping'][60]['physical_start'])
        self.assertEqual(payload['mapping'][60]['template_label'], '10:10-10:20')

    def test_saved_real_workbook_matches_model_and_template(self):
        result = verify_candidate(
            ROOT / 'outputs/q1_real_candidate_20260911/result1_candidate.xlsx',
            TEMPLATE, self.payload(allow_real_candidate=True))
        self.assertTrue(result['numeric_readback_passed'])
        self.assertEqual(result['cells_verified'], 158)
        self.assertEqual(result['style_changes'], [])
        self.assertTrue(result['unrelated_values_unchanged'])
        self.assertTrue(result['nonworksheet_package_preserved'])
        self.assertFalse(result['semantic_acceptance'])
