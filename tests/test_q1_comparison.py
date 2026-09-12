"""Synthetic strategy comparisons and terminal-feasibility regressions."""

from dataclasses import replace
import unittest
from unittest.mock import patch

import numpy as np

from src.core import BatteryParams
from src.core.solver import SolveResult
from src.q1 import compare_q1_strategies
from src.q1.baselines import RuleConfig, no_storage_baseline, rule_baseline
from src.q1.solve import prepare_q1_inputs


def inputs():
    return dict(load_kwh=np.zeros(144), pv_forecast_kwh=np.zeros(144),
                price_yuan_per_kwh=np.ones(144), initial_energy_kwh=6000,
                battery_params=BatteryParams(.9, .9, "bus"), slot_ids=list(range(144)),
                input_metadata={"input_kind": "synthetic", "data_version": "comparison-test-v1",
                                "mapping_version": "synthetic-144", "assumptions_version": "0.9-bus"})


class ComparisonTests(unittest.TestCase):
    def check_feasible(self, result, target=6000):
        self.assertEqual(result.status, "feasible", result.message)
        self.assertTrue(result.diagnostics["passed"])
        self.assertAlmostEqual(result.schedule["E"][0], target)
        self.assertAlmostEqual(result.schedule["E"][-1], target)
        s = result.schedule
        np.testing.assert_allclose(np.diff(s["E"]), .9 * s["C"] - s["D"] / .9, atol=1e-6, rtol=0)
        self.assertFalse(((s["C"] > 1e-6) & (s["D"] > 1e-6)).any())

    def test_no_storage_exposes_full_schedule_and_cost(self):
        args = inputs(); args["load_kwh"][:2] = [10, 20]; args["pv_forecast_kwh"][:2] = [50, 0]
        m, p, _ = prepare_q1_inputs(**args)
        r = no_storage_baseline(m, price_yuan_per_kwh=p)
        self.check_feasible(r)
        self.assertEqual(r.objective_yuan, 20)
        self.assertEqual(r.schedule["W"][0], 40)
        self.assertEqual(r.schedule["C"].sum(), 0)

    def test_rule_and_optimizer_both_match_hand_arbitrage(self):
        args = inputs(); args["load_kwh"][-1] = 81; args["price_yuan_per_kwh"][0] = .5
        report = compare_q1_strategies(**args)
        self.assertEqual(report["status"], "passed")
        self.check_feasible(report["strategies"]["rule"])
        costs = {row["strategy"]: row["cost_yuan"] for row in report["summary"]}
        self.assertAlmostEqual(costs["no_storage"], 81)
        self.assertAlmostEqual(costs["rule"], 50)
        self.assertAlmostEqual(costs["optimized"], 50)

    def test_flat_price_has_no_grid_charging(self):
        args = inputs(); args["load_kwh"][:] = 20
        report = compare_q1_strategies(**args)
        self.assertEqual(report["status"], "passed")
        for row in report["summary"]:
            self.assertAlmostEqual(row["cost_yuan"], 2880)
        self.assertEqual(report["strategies"]["rule"].schedule["C"].sum(), 0)

    def test_pv_first_can_shift_free_energy_at_flat_price(self):
        args = inputs(); args["pv_forecast_kwh"][0] = 100; args["load_kwh"][-1] = 81
        m, p, _ = prepare_q1_inputs(**args)
        r = rule_baseline(m, price_yuan_per_kwh=p)
        self.check_feasible(r)
        self.assertAlmostEqual(r.objective_yuan, 0)

    def test_terminal_projection_executes_discharge_instead_of_resetting(self):
        args = inputs(); args["pv_forecast_kwh"][0] = 100
        args["load_kwh"][1] = 81; args["price_yuan_per_kwh"][1] = .5
        m, p, _ = prepare_q1_inputs(**args)
        r = rule_baseline(m, price_yuan_per_kwh=p)
        self.check_feasible(r)
        # Demand at a mid-price is skipped by this intentionally simple rule.
        # End-of-day stored energy is physically discharged to surplus, paid for in full.
        self.assertAlmostEqual(r.schedule["D"][-1], 81)
        self.assertAlmostEqual(r.schedule["W"][-1], 81)
        self.assertIn(143, r.metadata["clipped_preference_slots"])
        self.assertAlmostEqual(r.objective_yuan, 40.5)

    def test_zero_power_and_boundary_initial_states(self):
        for initial in [1200, 10800]:
            for side in ["bus", "battery"]:
                args = inputs(); args["initial_energy_kwh"] = initial
                args["load_kwh"][-1] = 100; args["pv_forecast_kwh"][0] = 200
                args["battery_params"] = replace(args["battery_params"], power_reference_side=side,
                                                   max_charge_kw=0, max_discharge_kw=0)
                m, p, _ = prepare_q1_inputs(**args)
                r = rule_baseline(m, price_yuan_per_kwh=p)
                self.check_feasible(r, initial)
                self.assertAlmostEqual(r.objective_yuan, 100)

    def test_seeded_days_feasible_and_optimized_no_worse_than_both(self):
        for seed in range(5):
            rng = np.random.default_rng(seed + 20); args = inputs()
            args["load_kwh"] = rng.uniform(0, 1200, 144)
            args["pv_forecast_kwh"] = rng.uniform(0, 1600, 144)
            args["price_yuan_per_kwh"] = rng.uniform(.2, 1.2, 144)
            original = args["load_kwh"].copy()
            report = compare_q1_strategies(**args)
            self.assertEqual(report["status"], "passed", seed)
            self.check_feasible(report["strategies"]["rule"])
            optimized = report["strategies"]["optimized"].objective_yuan
            for name in ["no_storage", "rule"]:
                self.assertLessEqual(optimized, report["strategies"][name].objective_yuan + 1e-6)
            np.testing.assert_array_equal(original, args["load_kwh"])

    def test_zero_baseline_has_no_fabricated_percentage(self):
        report = compare_q1_strategies(**inputs())
        self.assertEqual(report["status"], "passed")
        self.assertTrue(all(row["saving_fraction_vs_no_storage"] is None for row in report["summary"]))

    def test_failed_optimizer_cannot_produce_successful_comparison(self):
        with patch("src.q1.compare.solve_q1", return_value=SolveResult("limit", "timeout", "highs_lp")):
            report = compare_q1_strategies(**inputs())
        self.assertEqual(report["status"], "comparison_failed")
        self.assertEqual(report["failed_strategy"], "optimized")
        self.assertEqual(report["summary"], [])

    def test_invalid_thresholds_rejected(self):
        for low, high in [(0.8, 0.2), (0.5, 0.5), (-1, 1), (0, float('nan'))]:
            with self.assertRaises(ValueError): RuleConfig(low, high)


if __name__ == "__main__":
    unittest.main()
