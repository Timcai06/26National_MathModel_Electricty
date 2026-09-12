import json
from pathlib import Path
import unittest

from src.core import BatteryParams
from src.core.solver import SolveResult
from src.q1.solve import prepare_q1_inputs
from src.q1.tables import TableTimeContract,extract_q1_tables
from datetime import date,datetime

ROOT=Path(__file__).resolve().parents[1]


class RealCandidateTests(unittest.TestCase):
    def setUp(self):
        self.report=json.loads((ROOT/'analysis/real_q1_candidate/result.json').read_text())['report']
        inputs=dict(self.report['input'])
        inputs['battery_params']=BatteryParams(**inputs['battery_params'])
        self.model,self.price,_=prepare_q1_inputs(**inputs)
        t=self.report['tables']['optimized']
        self.contract=TableTimeContract(date.fromisoformat(t['day']),tuple(datetime.fromisoformat(b) for b in t['physical_boundaries']),t['metadata']['mapping_version'],t['time_contract_status'])
        self.result=SolveResult(**self.report['comparison']['strategies']['optimized'])

    def extract(self,**kwargs):
        return extract_q1_tables(self.result,model=self.model,price_yuan_per_kwh=self.price,
            time_contract=self.contract,strategy='optimized',**kwargs)

    def test_candidate_is_rejected_by_default(self):
        with self.assertRaises(ValueError):self.extract()

    def test_explicit_candidate_keeps_unaccepted_status(self):
        t=self.extract(allow_candidate_time=True)
        self.assertEqual(t['time_contract_status'],'candidate')
        self.assertEqual(t['metadata']['input_kind'],'standardized')
        self.assertEqual(t['table1'],self.report['tables']['optimized']['table1'])

    def test_candidate_flag_does_not_bypass_physics(self):
        self.result.schedule['E'][10]+=10
        with self.assertRaises(ValueError):self.extract(allow_candidate_time=True)
