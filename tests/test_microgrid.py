"""Synthetic-only physics/solver tests; no original or teammate data is read."""

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from src.core import BatteryParams, build_microgrid_constraints, solve_model
from src.core.solver import _run_backend
from src.core.validation import validate_solution
from src.q1 import solve_q1


BATTERY = BatteryParams(charge_efficiency=.9, discharge_efficiency=.9, power_reference_side="bus")
META = {"input_kind": "synthetic", "data_version": "test-v1",
        "mapping_version": "synthetic-ordered-v1", "assumptions_version": "candidate-0.9-bus"}


def model(load, pv, **kwargs):
    return build_microgrid_constraints(load_kwh=load, pv_kwh=pv,
        battery_params=kwargs.pop("battery_params", BATTERY),
        initial_energy_kwh=kwargs.pop("initial_energy_kwh", 6000),
        terminal_energy_kwh=kwargs.pop("terminal_energy_kwh", 6000), **kwargs)


class PhysicsTests(unittest.TestCase):
    def check_optimal(self, result):
        self.assertEqual(result.status, "optimal", result.message)
        self.assertTrue(result.diagnostics["passed"])
        return result.schedule

    def test_two_slot_arbitrage_matches_hand_solution(self):
        result = solve_model(model([0, 81], [0, 0]), price_yuan_per_kwh=[.5, 1])
        s = self.check_optimal(result)
        self.assertAlmostEqual(result.objective_yuan, 50)
        np.testing.assert_allclose(s["G"], [100, 0], atol=1e-7)
        np.testing.assert_allclose(s["C"], [100, 0], atol=1e-7)
        np.testing.assert_allclose(s["D"], [0, 81], atol=1e-7)
        np.testing.assert_allclose(s["E"], [6000, 6090, 6000], atol=1e-7)

    def test_small_price_gap_does_not_pay_for_losses(self):
        r = solve_model(model([0, 81], [0, 0]), price_yuan_per_kwh=[.9, 1])
        self.check_optimal(r)
        self.assertAlmostEqual(r.objective_yuan, 81)

    def test_no_pv_flat_price_matches_no_storage(self):
        r = solve_model(model([20, 30], [0, 0]), price_yuan_per_kwh=[.5, .5])
        self.check_optimal(r)
        self.assertAlmostEqual(r.objective_yuan, 25)

    def test_pv_stored_with_correct_roundtrip_loss(self):
        r = solve_model(model([0, 81], [100, 0]), price_yuan_per_kwh=[1, 1])
        s = self.check_optimal(r)
        self.assertAlmostEqual(r.objective_yuan, 0)
        self.assertAlmostEqual(s["E"][1], 6090)

    def test_surplus_with_no_storage_is_not_sold(self):
        b = replace(BATTERY, max_charge_kw=0, max_discharge_kw=0)
        r = solve_model(model([10], [100], battery_params=b), price_yuan_per_kwh=[1])
        s = self.check_optimal(r)
        self.assertAlmostEqual(s["G"][0], 0)
        self.assertAlmostEqual(s["W"][0], 90)

    def test_explicit_terminal_target_and_free_terminal(self):
        fixed = solve_model(model([0], [0], terminal_energy_kwh=6090), price_yuan_per_kwh=[1])
        self.check_optimal(fixed)
        self.assertAlmostEqual(fixed.objective_yuan, 100)
        free = solve_model(model([90], [0], terminal_energy_kwh=None), price_yuan_per_kwh=[1])
        s = self.check_optimal(free)
        self.assertAlmostEqual(free.objective_yuan, 0)
        # With a free terminal and unpriced surplus, many final states tie.
        # Do not mistake one economically arbitrary optimum for an exact target.
        self.assertLessEqual(s["E"][-1], 5900 + 1e-6)
        self.assertAlmostEqual(s["E"][-1], 6000 - s["D"].sum() / .9)

    def test_soc_lower_and_upper_are_enforced(self):
        for initial in [1200, 10800]:
            with self.subTest(initial=initial):
                m = model([0, 1000], [10000, 0], initial_energy_kwh=initial, terminal_energy_kwh=initial)
                r = solve_model(m, price_yuan_per_kwh=[.1, 1])
                s = self.check_optimal(r)
                self.assertGreaterEqual(s["E"].min(), 1200 - 1e-6)
                self.assertLessEqual(s["E"].max(), 10800 + 1e-6)

    def test_bus_power_limit_changes_optimum(self):
        b = replace(BATTERY, max_charge_kw=300)
        r = solve_model(model([0, 81], [0, 0], battery_params=b), price_yuan_per_kwh=[.5, 1])
        s = self.check_optimal(r)
        self.assertAlmostEqual(s["C"][0], 50)
        self.assertAlmostEqual(r.objective_yuan, 65.5)

    def test_battery_side_power_limit_converts_to_bus_side(self):
        b = replace(BATTERY, power_reference_side="battery", max_charge_kw=540)
        r = solve_model(model([0, 81], [0, 0], battery_params=b), price_yuan_per_kwh=[.5, 1])
        self.check_optimal(r)
        self.assertAlmostEqual(r.objective_yuan, 50)

    def test_fixed_contract_and_emergency_switch(self):
        m = model([100], [0], fixed_purchase_kwh=[20], emergency_enabled=True)
        r = solve_model(m, price_yuan_per_kwh=[1], emergency_price_yuan_per_kwh=[5])
        s = self.check_optimal(r)
        self.assertAlmostEqual(s["G"][0], 20)
        self.assertAlmostEqual(s["U"][0], 80)
        self.assertAlmostEqual(r.objective_yuan, 420)
        off = solve_model(model([100], [0], fixed_purchase_kwh=[20]), price_yuan_per_kwh=[1])
        self.assertEqual(off.status, "infeasible")
        self.assertIsNone(off.schedule)

    def test_unreachable_terminal_is_not_fake_success(self):
        r = solve_model(model([0], [0], terminal_energy_kwh=10800), price_yuan_per_kwh=[1])
        self.assertEqual(r.status, "infeasible")
        self.assertIsNone(r.objective_yuan)
        self.assertIsNone(r.schedule)

    def test_direct_milp_matches_hand_solution(self):
        r = solve_model(model([0, 81], [0, 0]), price_yuan_per_kwh=[.5, 1], mode="milp")
        self.check_optimal(r)
        self.assertEqual(r.backend, "highs_milp")
        self.assertAlmostEqual(r.objective_yuan, 50)

    def test_auto_fallback_uses_real_milp_after_valid_degenerate_lp(self):
        m = model([0], [0])
        x = np.zeros(len(m.lower))
        for key, value in {"G": 19, "C": 100, "D": 81, "E": 6000}.items():
            x[m.layout[key]] = value
        # At zero price this physically valid cycling LP solution is optimal.
        first = SimpleNamespace(status=0, message="injected degenerate LP optimum", x=x, fun=0)
        calls = []
        def backend(mm, obj, seconds):
            calls.append(mm.mutual_exclusion)
            return first if len(calls) == 1 else _run_backend(mm, obj, seconds)
        with patch("src.core.solver._run_backend", side_effect=backend):
            r = solve_model(m, price_yuan_per_kwh=[0])
        self.check_optimal(r)
        self.assertEqual(calls, [False, True])
        self.assertEqual(r.attempts[0]["fallback_reason"], "simultaneous_charge_and_discharge")

    def test_independent_validator_detects_tampered_energy(self):
        m = model([10], [0])
        x = np.zeros(len(m.lower)); x[m.layout["G"]] = 10; x[m.layout["E"]] = 6000
        self.assertTrue(validate_solution(m, x)["passed"])
        x[m.layout["E"].stop - 1] += 1
        self.assertFalse(validate_solution(m, x)["passed"])
        x[0] = np.nan
        self.assertFalse(validate_solution(m, x)["passed"])

    def test_limit_status_discards_unverified_incumbent(self):
        raw = SimpleNamespace(status=1, message="time limit", x=np.ones(7), fun=0)
        with patch("src.core.solver._run_backend", return_value=raw):
            r = solve_model(model([0], [0]), price_yuan_per_kwh=[1])
        self.assertEqual(r.status, "limit")
        self.assertIsNone(r.schedule)

    def test_invalid_inputs_are_rejected_without_cleaning(self):
        for load,pv in [([],[]), ([1,2],[1]), ([np.nan],[0]), ([1],[-1]), ([[1]],[[0]])]:
            with self.subTest(load=load), self.assertRaises(ValueError): model(load,pv)
        with self.assertRaises(ValueError): replace(BATTERY, charge_efficiency=0)
        with self.assertRaises(ValueError): replace(BATTERY, power_reference_side="auto")
        with self.assertRaises(ValueError): model([0],[0],initial_energy_kwh=0)
        with self.assertRaises(ValueError): solve_model(model([0],[0]),price_yuan_per_kwh=[-1])
        with self.assertRaises(ValueError): solve_model(model([0],[0],emergency_enabled=True),price_yuan_per_kwh=[1])


class Q1Tests(unittest.TestCase):
    def args(self):
        return dict(load_kwh=np.zeros(144), pv_forecast_kwh=np.zeros(144),
                    price_yuan_per_kwh=np.ones(144), initial_energy_kwh=6000,
                    battery_params=BATTERY, slot_ids=list(range(144)), input_metadata=META)

    def test_full_day_arbitrage_and_result_dimensions(self):
        args=self.args();args['load_kwh'][-1]=81;args['price_yuan_per_kwh'][0]=.5
        r=solve_q1(**args)
        self.assertEqual(r.status,'optimal',r.message)
        self.assertAlmostEqual(r.objective_yuan,50)
        self.assertAlmostEqual(r.metadata['saving_vs_no_storage_yuan'],31)
        self.assertEqual(len(r.schedule['E']),145)
        self.assertEqual(len(r.schedule['G']),144)
        self.assertFalse(r.metadata['time_semantics_verified_by_solver'])

    def test_four_seeded_days_against_independent_baseline_and_conservation(self):
        for seed in range(4):
            args=self.args();rng=np.random.default_rng(seed)
            args['load_kwh']=rng.uniform(100,700,144)
            args['pv_forecast_kwh']=rng.uniform(0,900,144)
            args['price_yuan_per_kwh']=rng.uniform(.2,1.2,144)
            r=solve_q1(**args)
            self.assertEqual(r.status,'optimal',f'seed {seed}: {r.message}')
            s=r.schedule
            self.assertLessEqual(r.objective_yuan,np.maximum(args['load_kwh']-args['pv_forecast_kwh'],0)@args['price_yuan_per_kwh']+1e-6)
            np.testing.assert_allclose(s['G']+args['pv_forecast_kwh']+s['D'],args['load_kwh']+s['C']+s['W'],atol=1e-6,rtol=0)
            self.assertAlmostEqual(s['G'].sum(),args['load_kwh'].sum()-args['pv_forecast_kwh'].sum()+.19*s['C'].sum()+s['W'].sum(),places=6)
            self.assertFalse(((s['C']>1e-6)&(s['D']>1e-6)).any())

    def test_reject_wrong_horizon_order_and_missing_provenance(self):
        for key,value in [('load_kwh',[0]),('slot_ids',list(reversed(range(144)))),('input_metadata',{})]:
            args=self.args();args[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):solve_q1(**args)


if __name__ == '__main__':
    unittest.main()
