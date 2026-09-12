from datetime import date, timedelta
import unittest
import numpy as np

from src.core import BatteryParams
from src.q2.forecast import ActualDay, midnight
from src.q2.execution import CausalExecutor, OBSERVATION_POLICY
from src.q3.pv import PublishedPV
from src.q3.planning import adjustment_cost, replan
from scripts.run_real_q23 import execute_day
from src.q3.reporting import emergency_intervals
from scripts.verify_real_q23 import check_day
import copy


class PVConversionTests(unittest.TestCase):
    def test_constant_preserves_energy_and_units(self):
        issue = midnight(date(2025, 12, 31))+timedelta(hours=18)
        for method in ('linear', 'step'):
            result = PublishedPV(issue, np.full(24, 60)).energy(decision_time=issue, method=method)
            np.testing.assert_allclose(result, 10)
            self.assertEqual(sum(result), 1440)

    def test_linear_integral_and_first_hour(self):
        issue = midnight(date(2025, 1, 1))
        result = PublishedPV(issue, np.arange(1, 25)*60).energy(decision_time=issue)
        np.testing.assert_allclose(result[:6], 10)
        self.assertAlmostEqual(sum(result[6:12]), 90)
        self.assertAlmostEqual(result[6], 65/6)

    def test_unpublished_and_incomplete_forecasts_rejected(self):
        issue = midnight(date(2025, 1, 1))
        forecast = PublishedPV(issue, np.ones(24))
        with self.assertRaises(ValueError):
            forecast.energy(decision_time=issue-timedelta(seconds=1))
        with self.assertRaises(ValueError):
            PublishedPV(issue, np.ones(23))


class RollingContractTests(unittest.TestCase):
    def test_sequential_settlement_has_no_duplicate_refund(self):
        self.assertEqual(100+adjustment_cost([100], [80], [1]), 90)
        self.assertEqual(100+adjustment_cost([100], [80], [1])+adjustment_cost([80], [100], [1]), 120)
        self.assertEqual(100+adjustment_cost([100], [80], [1], refund=False), 110)

    def test_piecewise_solver_agrees_with_hand_solution(self):
        for refund in (True, False):
            for load in (80, 120):
                result = replan(load_kwh=[load], pv_kwh=[0], old_commitment=[100], price=[1],
                    initial_energy=6000, battery=BatteryParams(.9, .9, 'bus'), refund=refund)
                # No refund: keep an already-paid surplus instead of paying to cancel it.
                expected = load if refund else max(100, load)
                self.assertAlmostEqual(result['G'][0], expected)
                self.assertTrue(result['diagnostics']['passed'])
                self.assertLess(result['objective_residual_yuan'], 1e-6)

    def test_cannot_rewrite_past_or_revise_between_boundaries(self):
        day = date(2025, 2, 1)
        executor = CausalExecutor(day=day, commitment_kwh=np.ones(144), price_yuan_per_kwh=np.ones(144),
            price_available_at=midnight(day), battery_params=BatteryParams(.9, .9, 'bus'),
            initial_energy_kwh=6000, terminal_energy_kwh=6000, emergency_multiplier=5,
            observation_policy=OBSERVATION_POLICY)
        with self.assertRaises(ValueError):
            executor.revise_commitment(commitment_kwh=np.ones(144), issue_time=midnight(day))
        for i in range(36):
            executor.step(slot_id=i, load_kwh=1, pv_kwh=0, available_at=midnight(day)+timedelta(minutes=10*(i+1)))
        changed = np.ones(144)
        changed[0] = 2
        with self.assertRaises(ValueError):
            executor.revise_commitment(commitment_kwh=changed, issue_time=midnight(day)+timedelta(hours=6))

    def test_future_actual_changes_cannot_change_earlier_plans(self):
        day = date(2025, 2, 1)
        issue = midnight(day)
        forecasts = {issue+timedelta(hours=h): PublishedPV(issue+timedelta(hours=h), np.zeros(24)) for h in (0,6,12,18)}
        load = np.full(144, 100.)
        def run(values):
            actual = ActualDay(day, values, np.zeros(144), issue+timedelta(days=1))
            return execute_day(actual, np.ones(144), 6000, {'load': load, 'pv': np.zeros(144)}, {},
                published=forecasts, update_hours=(6,12,18))
        before = run(load)
        altered = load.copy()
        altered[120:] += 200
        after = run(altered)
        self.assertEqual(before['planned_G'], after['planned_G'])
        self.assertEqual(before['revisions'], after['revisions'])
        self.assertNotEqual(before['schedule']['U'], after['schedule']['U'])

    def test_grouping_respects_gaps_and_midnight(self):
        values = np.zeros(144)
        values[0:2], values[3], values[143] = [2,3], 4, 5
        groups = emergency_intervals(values)
        self.assertEqual([r['interval'] for r in groups], ['0:00-0:20','0:30-0:40','23:50-24:00'])
        self.assertEqual(sum(r['purchase_kwh'] for r in groups), 14)
        self.assertEqual(emergency_intervals(np.zeros(144)), [])

    def test_independent_replay_rejects_physical_and_ledger_tampering(self):
        day = date(2025,2,1)
        actual = ActualDay(day, np.full(144,100.), np.zeros(144), midnight(day)+timedelta(days=1))
        record = execute_day(actual, np.ones(144), 6000,
            {'load': np.full(144,100.), 'pv': np.zeros(144)}, {})
        check_day(record, actual, np.ones(144), 6000, True)
        for field in ('energy', 'cost', 'commitment'):
            altered = copy.deepcopy(record)
            if field == 'energy': altered['schedule']['E'][20] += 1
            elif field == 'cost': altered['costs']['total_yuan'] += 1
            else: altered['planned_G'][0] += 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                check_day(altered, actual, np.ones(144), 6000, True)
