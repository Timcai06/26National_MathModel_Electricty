import unittest
from scripts.deliver_real_q23 import verify


class AnnualCandidateExcelTests(unittest.TestCase):
    def test_q2_saved_values_dates_and_template(self):
        result = verify(2)
        self.assertEqual(result['numeric_cells_verified'], 54314)
        self.assertTrue(result['template_styles_preserved'])
        self.assertFalse(result['semantic_acceptance'])

    def test_q3_saved_values_dates_and_template(self):
        result = verify(3)
        self.assertEqual(result['numeric_cells_verified'], 102919)
        self.assertTrue(result['template_styles_preserved'])
        self.assertFalse(result['semantic_acceptance'])
