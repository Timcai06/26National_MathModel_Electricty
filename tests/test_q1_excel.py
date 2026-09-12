import copy
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from src.q1.excel import OUTPUT_POLICY, candidate_payload, verify_candidate

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'CUMCM2026Problems/C题/附件/附件5/result1.xlsx'
CANDIDATE = ROOT / 'outputs/q1_candidate_20260911/result1_synthetic_candidate.xlsx'


class ExcelContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((ROOT/'analysis/q1_tables/tables.json').read_text())['reports']['seeded_variable_day']

    def payload(self, report=None):
        return candidate_payload(report or self.report, TEMPLATE, output_policy=OUTPUT_POLICY)

    def test_full_mapping_and_endpoint_cells(self):
        p = self.payload()
        self.assertEqual(sum(map(len, p['cells'].values())), 158)
        self.assertEqual(p['mapping'][60]['cell'], 'B62')
        self.assertIn('T10:00:', p['mapping'][60]['physical_start'])
        self.assertEqual(p['mapping'][60]['template_label'], '10:10-10:20')
        self.assertEqual(p['cells']['充放电量']['E2'], 6000)
        self.assertEqual(p['cells']['充放电量']['E3'], 6000)
        self.assertFalse(p['semantic_acceptance'])

    def test_final_saved_workbook(self):
        r = verify_candidate(CANDIDATE, TEMPLATE, self.payload())
        self.assertEqual(r['cells_verified'], 158)
        self.assertEqual(r['style_changes'], [])
        self.assertTrue(r['nonworksheet_package_preserved'])

    def test_reject_real_input_and_unstated_mapping(self):
        report = copy.deepcopy(self.report)
        report['input']['input_metadata']['input_kind'] = 'standardized'
        with self.assertRaises(ValueError): self.payload(report)
        with self.assertRaises(ValueError):
            candidate_payload(self.report, TEMPLATE, output_policy='accepted')

    def test_reject_stale_tables_and_provenance(self):
        for kind in ['table', 'metadata']:
            report = copy.deepcopy(self.report)
            if kind == 'table': report['tables']['optimized']['table2'][0]['charge_bus_kwh'] += 1
            else: report['input']['input_metadata']['data_version'] = 'changed'
            with self.subTest(kind=kind), self.assertRaises(ValueError): self.payload(report)

    def test_blank_template_is_not_a_completed_result(self):
        with self.assertRaisesRegex(ValueError, 'Numeric readback mismatch'):
            verify_candidate(TEMPLATE, TEMPLATE, self.payload())

    def test_readback_detects_corrupted_value_and_label(self):
        for part, old, new in [('xl/worksheets/sheet2.xml','<v>6000</v>','<v>6001</v>'),
                               ('xl/sharedStrings.xml','时间段','坏标签')]:
            with self.subTest(part=part), tempfile.TemporaryDirectory() as folder:
                path = Path(folder)/'corrupt.xlsx'
                with ZipFile(CANDIDATE) as src, ZipFile(path,'w') as dst:
                    for item in src.infolist():
                        content = src.read(item.filename)
                        if item.filename == part:
                            text = content.decode('utf-8')
                            self.assertIn(old, text)
                            content = text.replace(old,new,1).encode('utf-8')
                        dst.writestr(item,content)
                with self.assertRaises(ValueError): verify_candidate(path,TEMPLATE,self.payload())

    def test_template_hash_mismatch_is_rejected(self):
        p = self.payload()
        p['template_sha256'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'Original template changed'):
            verify_candidate(CANDIDATE,TEMPLATE,p)
