import unittest
from datetime import date, timedelta
import numpy as np
from src.q2.forecast import ActualDay, midnight
from src.q2.residual_margin import MarginConfig, safety_forecast
from src.q2.oracle import solve_oracle_day
from src.core.model import BatteryParams


class MarginTests(unittest.TestCase):
    def history(self, n=14):
        first = date(2025,1,1)
        return [ActualDay(first+timedelta(days=i), np.full(144,200.+10*i), np.zeros(144),
            midnight(first+timedelta(days=i+1))) for i in range(n)]

    def run_margin(self, history, target=date(2025,1,15), config=MarginConfig(.8,.5)):
        return safety_forecast(history, target_day=target, baseline_load=np.full(144,270.),
                               baseline_pv=np.zeros(144), config=config)

    def test_raw_quantile_not_double_bias(self):
        pred,audit = self.run_margin(self.history())
        np.testing.assert_array_equal(pred['load'], np.full(144,305.))
        self.assertEqual(audit['bucket_raw_quantiles_kwh'], [70.]*6)
        self.assertEqual(len(audit['residual_days']),7)
        self.assertFalse(pred['pv'].flags.writeable)

    def test_future_or_unpublished_history_rejected(self):
        with self.assertRaises(ValueError):
            self.run_margin(self.history(15))
        h=self.history()
        h[-1]=ActualDay(h[-1].day,h[-1].load_kwh,h[-1].pv_kwh,midnight(date(2025,1,16)))
        with self.assertRaises(ValueError):
            self.run_margin(h)

    def test_zero_margin_and_insufficient_history(self):
        p,a=self.run_margin(self.history(),config=MarginConfig(.8,0.))
        np.testing.assert_array_equal(p['load'],np.full(144,270.))
        p,a=self.run_margin(self.history(10))
        self.assertEqual(a['fallback'],'zero_margin_insufficient_history')
        self.assertEqual(sum(a['correction_kwh']),0.)

    def test_window_and_config(self):
        p,a=self.run_margin(self.history(40),target=date(2025,2,10))
        self.assertEqual(len(a['residual_days']),28)
        with self.assertRaises(ValueError): MarginConfig(.8,1.,bucket_slots=13)
        with self.assertRaises(ValueError): MarginConfig(.8,float('nan'))
        with self.assertRaises(ValueError): MarginConfig(1.,1.)


class OracleTests(unittest.TestCase):
    def test_bounds_and_fixed_contract(self):
        load=np.full(144,120.)
        pv=np.zeros(144)
        g=np.full(144,60.)
        price=np.full(144,.5)
        battery=BatteryParams(.9,.9,'bus')
        fixed=solve_oracle_day(actual_load=load,actual_pv=pv,price=price,battery=battery,fixed_commitment=g)
        full=solve_oracle_day(actual_load=load,actual_pv=pv,price=price,battery=battery)
        feasible_no_storage=float(price@g+5*price@np.maximum(load-g,0))
        self.assertLessEqual(fixed['costs']['total_yuan'],feasible_no_storage+1e-6)
        self.assertLessEqual(full['costs']['total_yuan'],fixed['costs']['total_yuan']+1e-6)
        self.assertAlmostEqual(full['costs']['total_yuan'],float(price@load),places=5)
        np.testing.assert_array_equal(fixed['planned_G'],g)
        self.assertEqual(fixed['policy'],'perfect_information_diagnostic_not_causal')
        for result in (full,fixed):
            self.assertTrue(result['diagnostics']['passed'])
            self.assertAlmostEqual(result['schedule']['E'][0],6000.)
            self.assertAlmostEqual(result['schedule']['E'][-1],6000.)


if __name__=='__main__': unittest.main()
