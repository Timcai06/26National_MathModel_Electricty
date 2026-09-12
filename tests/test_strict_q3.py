import unittest
from datetime import date,timedelta
import numpy as np
from src.q2.forecast import ActualDay,midnight
from src.q3.pv import PublishedPV
from src.q3.strict_execution import StrictRollingExecutor
from scripts.run_real_q23 import BATTERY
from scripts.run_strict_q3 import execute_day


class StrictQ3Tests(unittest.TestCase):
    def setUp(self):
        self.day=date(2025,2,1);self.start=midnight(self.day)
        self.pred={'load':np.full(144,120.),'pv':np.zeros(144)}
        self.price=np.full(144,.5);self.g=np.full(144,120.)
        self.published={self.start+timedelta(hours=h):PublishedPV(self.start+timedelta(hours=h),np.full(24,100. if h else 0.)) for h in (0,6,12,18)}

    def actual(self,value):
        return ActualDay(self.day,np.full(144,value),np.zeros(144),self.start+timedelta(days=1))

    def run_day(self,actual,published,control='fresh'):
        return execute_day(actual,self.price,self.pred,{},self.g,published,6000.,control)

    def test_future_actual_does_not_change_contract_or_battery(self):
        a=self.run_day(self.actual(0.),self.published)
        b=self.run_day(self.actual(2000.),self.published)
        self.assertEqual(a['commands'],b['commands'])
        self.assertEqual(a['revisions'],b['revisions'])
        self.assertGreater(b['costs']['emergency_yuan'],a['costs']['emergency_yuan'])
        self.assertLess(b['ledger_residual_yuan'],1e-6)

    def test_future_forecast_cannot_change_earlier_actions(self):
        other=dict(self.published)
        other[self.start+timedelta(hours=12)]=PublishedPV(self.start+timedelta(hours=12),np.full(24,2000.))
        a=self.run_day(self.actual(120.),self.published)
        b=self.run_day(self.actual(120.),other)
        self.assertEqual(a['commands'][:72],b['commands'][:72])
        self.assertEqual(a['revisions'][0],b['revisions'][0])
        self.assertNotEqual(a['revisions'][1]['new_remaining_kwh'],b['revisions'][1]['new_remaining_kwh'])

    def test_unpublished_forecast_rejected(self):
        wrong=dict(self.published)
        wrong[self.start+timedelta(hours=6)]=PublishedPV(self.start+timedelta(hours=12),np.zeros(24))
        with self.assertRaises(ValueError):self.run_day(self.actual(120.),wrong)

    def test_past_contract_and_pending_command_protected(self):
        c=StrictRollingExecutor(day=self.day,commitment=self.g,price=self.price,
            forecast_load=self.pred['load'],forecast_pv=self.pred['pv'],forecast_available_at=self.start,
            battery=BATTERY)
        for i in range(36):
            c.decide(self.start+timedelta(minutes=10*i))
            c.settle(load_kwh=120.,pv_kwh=0.,available_at=self.start+timedelta(minutes=10*(i+1)))
        args=dict(commitment=self.g.copy(),remaining_load=np.full(108,120.),remaining_pv=np.zeros(108),
                  decision_time=self.start+timedelta(hours=6),forecast_available_at=self.start)
        bad=dict(args);bad['commitment']=self.g.copy();bad['commitment'][0]+=1
        with self.assertRaises(ValueError):c.revise(**bad)
        c.revise(**args)
        with self.assertRaises(ValueError):c.revise(**args)
        c.decide(self.start+timedelta(hours=6))
        with self.assertRaises(ValueError):c.revise(**args)

    def test_stale_forecasts_and_zero_control(self):
        a=self.run_day(self.actual(120.),self.published,'stale')
        self.assertEqual([r['forecast_issue_time'] for r in a['revisions']],[self.start.isoformat()]*3)
        b=self.run_day(self.actual(120.),self.published,'zero')
        self.assertEqual(b['revisions'],[])
        self.assertEqual(b['costs']['adjustment_yuan'],0.)


if __name__=='__main__':unittest.main()
