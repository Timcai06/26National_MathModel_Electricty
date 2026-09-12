import unittest
from datetime import date,timedelta
import numpy as np
from src.q2.forecast import ActualDay,midnight
from src.q3.pv import PublishedPV
from src.q3.strict_execution import StrictRollingExecutor
from src.q3.voi import GateConfig,joint_scenarios,evaluate,variable_cost
from scripts.run_real_q23 import BATTERY
from scripts.run_q3_voi import execute_day


class VOITests(unittest.TestCase):
    def setUp(self):
        self.target=date(2025,1,15);self.start=midnight(self.target)
        self.history=[];self.published={}
        for i in range(15):
            day=date(2025,1,1)+timedelta(days=i)
            if i<14:self.history.append(ActualDay(day,np.full(144,120.),np.full(144,100/6),midnight(day)+timedelta(days=1)))
            for hour in (0,6,12,18):
                issue=midnight(day)+timedelta(hours=hour)
                self.published[issue]=PublishedPV(issue,np.full(24,0. if i==14 and hour==0 else 100.))
        self.load=np.full(144,120.);self.price=np.full(144,.5)

    def at_six(self):
        c=StrictRollingExecutor(day=self.target,commitment=self.load,price=self.price,
            forecast_load=self.load,forecast_pv=np.zeros(144),forecast_available_at=self.start,battery=BATTERY)
        for i in range(36):
            c.decide(self.start+timedelta(minutes=10*i))
            c.settle(load_kwh=0.,pv_kwh=0.,available_at=self.start+timedelta(minutes=10*(i+1)))
        return c

    def asof(self):
        return {k:v for k,v in self.published.items() if k<=self.start+timedelta(hours=6)}

    def test_joint_scenarios_and_no_future(self):
        paths,audit=joint_scenarios(self.history,self.asof(),decision_time=self.start+timedelta(hours=6),baseline_load=self.load)
        self.assertEqual(paths[0].shape,(7,108));self.assertEqual(audit['scenario_count'],7)
        np.testing.assert_allclose(paths[0],120.);np.testing.assert_allclose(paths[1],100/6)
        with self.assertRaises(ValueError):
            joint_scenarios(self.history,self.published,decision_time=self.start+timedelta(hours=6),baseline_load=self.load)
        future=ActualDay(self.target,self.load,np.zeros(144),self.start+timedelta(days=1))
        with self.assertRaises(ValueError):
            joint_scenarios([*self.history,future],self.asof(),decision_time=self.start+timedelta(hours=6),baseline_load=self.load)

    def test_acceptance_and_single_adjustment_charge(self):
        c=self.at_six()
        proposal,audit,previews=evaluate(c,decision_time=self.start+timedelta(hours=6),published_as_of=self.asof(),
            history=self.history,baseline_load=self.load,config=GateConfig())
        self.assertTrue(audit['accept']);self.assertGreater(audit['predicted_gain_yuan'],0.)
        paths,_=joint_scenarios(self.history,self.asof(),decision_time=self.start+timedelta(hours=6),baseline_load=self.load)
        raw=variable_cost(previews[1],*paths,self.price[36:])
        np.testing.assert_allclose(audit['update_scenario_costs'],raw+audit['adjustment_yuan'])
        self.assertEqual(len(c.records),36);self.assertEqual(c.last_revision_slot,0)
        _,disabled,_=evaluate(c,decision_time=self.start+timedelta(hours=6),published_as_of=self.asof(),
            history=self.history,baseline_load=self.load,config=GateConfig(enabled=False))
        self.assertFalse(disabled['accept'])

    def test_fallback_and_threshold_validation(self):
        c=self.at_six()
        proposal,audit,_=evaluate(c,decision_time=self.start+timedelta(hours=6),published_as_of=self.asof(),
            history=self.history[:10],baseline_load=self.load,config=GateConfig())
        self.assertIsNone(proposal);self.assertFalse(audit['accept'])
        with self.assertRaises(ValueError):GateConfig(float('inf'))

    def test_actuals_only_change_posthoc_and_settlement(self):
        def run(value):
            actual=ActualDay(self.target,np.full(144,value),np.zeros(144),self.start+timedelta(days=1))
            return execute_day(actual,self.price,{'load':self.load,'pv':np.zeros(144)}, {},self.load,
                self.published,self.history,self.load,6000.,GateConfig())
        a,b=run(0.),run(2000.)
        self.assertEqual(a['commands'],b['commands']);self.assertEqual(a['revisions'],b['revisions'])
        clean=lambda gates:[{k:v for k,v in g.items() if not k.startswith('posthoc_')} for g in gates]
        self.assertEqual(clean(a['gates']),clean(b['gates']))
        self.assertNotEqual(a['gates'][0]['posthoc_keep_variable_yuan'],b['gates'][0]['posthoc_keep_variable_yuan'])
        self.assertGreater(b['costs']['total_yuan'],a['costs']['total_yuan'])


if __name__=='__main__':unittest.main()
