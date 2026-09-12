from datetime import date,timedelta
from unittest.mock import patch
import unittest
import numpy as np

from src.core import BatteryParams
from src.core.solver import SolveResult
from src.q2.forecast import ActualDay,midnight
from src.q2.coordinator import PriceDay,compare_multiday
from src.q2.execution import OBSERVATION_POLICY


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        start=date(2026,1,1)
        self.days=[ActualDay(start+timedelta(days=i),np.full(144,100+i),np.full(144,20),
                            midnight(start+timedelta(days=i+1))) for i in range(12)]
        self.prices=[PriceDay(d.day,np.full(144,.5),midnight(d.day)) for d in self.days]
        self.args=dict(simulation_start=date(2026,1,8),evaluation_start=date(2026,1,9),end_day=date(2026,1,10),
            initial_energy_kwh=6000,initial_state_source='synthetic starting state',battery_params=BatteryParams(.9,.9,'bus'),
            terminal_policy='daily_neutral',emergency_multiplier=5,observation_policy=OBSERVATION_POLICY,
            metadata=dict(input_kind='synthetic',data_version='test',mapping_version='test',assumptions_version='test'))

    def run_case(self,days=None,prices=None,**changes):
        return compare_multiday(self.days if days is None else days,self.prices if prices is None else prices,**{**self.args,**changes})

    def test_warmup_separate_same_boundaries_and_cost_reconciliation(self):
        report=self.run_case()
        self.assertEqual(report['status'],'complete')
        self.assertTrue(report['cost_comparison_valid'])
        for result in report['strategies'].values():
            s=result['summary']
            self.assertEqual((s['warmup_days'],s['evaluation_days']),(1,2))
            actual=sum(d['execution']['costs']['total_yuan'] for d in result['daily'])
            self.assertAlmostEqual(actual,s['warmup_costs']['total_yuan']+s['evaluation_costs']['total_yuan'])
            self.assertEqual(s['max_cross_day_residual_kwh'],0)

    def test_free_terminal_carries_actual_state_without_reset(self):
        report=self.run_case(terminal_policy='cross_day_free')
        for result in report['strategies'].values():
            days=result['daily']
            self.assertNotEqual(days[0]['terminal_energy_kwh'],6000)
            for a,b in zip(days,days[1:]):
                self.assertEqual(a['terminal_energy_kwh'],b['initial_energy_kwh'])
                self.assertEqual(b['execution']['records'][0]['initial_energy_kwh'],a['terminal_energy_kwh'])

    def test_end_of_window_restore_is_executed(self):
        report=self.run_case(terminal_policy='cross_day_restore',evaluation_start=date(2026,1,8))
        self.assertTrue(report['cost_comparison_valid'])
        for result in report['strategies'].values():
            self.assertAlmostEqual(result['summary']['final_energy_kwh'],6000)

    def test_future_actual_change_preserves_earlier_days_and_today_plan(self):
        changed=[d if d.day!=date(2026,1,10) else ActualDay(d.day,np.full(144,999),d.pv_kwh,d.available_at) for d in self.days]
        a,b=self.run_case(),self.run_case(days=changed)
        for method in a['strategies']:
            old,new=a['strategies'][method]['daily'],b['strategies'][method]['daily']
            for x,y in zip(old,new):
                self.assertEqual(x['execution']['schedule']['G'],y['execution']['schedule']['G'])
                if x['day']<'2026-01-10':self.assertEqual(x['execution'],y['execution'])
            self.assertNotEqual(old[-1]['execution']['costs'],new[-1]['execution']['costs'])

    def test_history_failure_is_not_skipped_or_ranked(self):
        r=self.run_case(simulation_start=date(2026,1,2),evaluation_start=date(2026,1,2),end_day=date(2026,1,3))
        self.assertEqual(r['status'],'incomplete')
        self.assertFalse(r['cost_comparison_valid'])
        self.assertIsNone(r['strategies']['last_week']['summary'])
        self.assertEqual(r['strategies']['last_week']['failure']['stage'],'forecast')

    def test_planning_failure_is_not_a_zero_cost_day(self):
        with patch('src.q2.coordinator.plan_from_forecast',return_value=SolveResult('limit','timeout','test')):
            r=self.run_case()
        self.assertEqual(r['status'],'incomplete')
        for strategy in r['strategies'].values():
            self.assertIsNone(strategy['summary'])
            self.assertEqual(strategy['daily'],[])

    def test_missing_dates_and_late_prices_rejected(self):
        with self.assertRaises(ValueError):self.run_case(days=[d for d in self.days if d.day!=date(2026,1,9)])
        with self.assertRaises(ValueError):self.run_case(prices=self.prices[:8])
        prices=[p if p.day!=date(2026,1,9) else PriceDay(p.day,p.price_yuan_per_kwh,p.available_at+timedelta(seconds=1)) for p in self.prices]
        with self.assertRaises(ValueError):self.run_case(prices=prices)

    def test_unequal_boundary_energy_prevents_cost_ranking(self):
        # Different warmup forecast errors cause different evaluation starting states.
        days=[ActualDay(d.day,np.full(144,90 if i==7 else 100+i),d.pv_kwh,d.available_at) for i,d in enumerate(self.days)]
        r=self.run_case(days=days,terminal_policy='cross_day_free')
        self.assertEqual(r['status'],'complete')
        self.assertFalse(r['cost_comparison_valid'])
