import copy
from dataclasses import replace
from datetime import date, datetime, timedelta
import unittest

import numpy as np

from src.core import BatteryParams
from src.q1.solve import prepare_q1_inputs
from src.q1.compare import compare_q1_strategies
from src.q1.tables import TableTimeContract, ZONE, extract_q1_tables, render_q1_tables_markdown


class TableTests(unittest.TestCase):
    def setUp(self):
        self.inputs = dict(load_kwh=np.arange(144.), pv_forecast_kwh=np.zeros(144),
            price_yuan_per_kwh=np.full(144, .333333333), initial_energy_kwh=6000,
            battery_params=BatteryParams(.9, .9, "bus"), slot_ids=list(range(144)),
            input_metadata=dict(input_kind="synthetic", data_version="test-v1",
                                mapping_version="test-axis-v1", assumptions_version="test-v1"))
        self.model, self.price, _ = prepare_q1_inputs(**self.inputs)
        self.report = compare_q1_strategies(**self.inputs)
        start = datetime(2025, 12, 31, tzinfo=ZONE)
        self.contract = TableTimeContract(date(2025, 12, 31),
            tuple(start + timedelta(minutes=10*i) for i in range(145)), "test-axis-v1", "synthetic")
        self.result = self.report["strategies"]["no_storage"]

    def extract(self, result=None, contract=None, strategy="no_storage"):
        return extract_q1_tables(result or self.result, model=self.model,
            price_yuan_per_kwh=self.price, time_contract=contract or self.contract, strategy=strategy)

    def test_selected_physical_slots_and_full_day_totals(self):
        t = self.extract()
        self.assertEqual([r["purchase_kwh"] for r in t["table1"]], [60, 72, 84, 96, 108, 120])
        self.assertEqual(t["daily_totals"]["purchase_kwh"], sum(range(144)))
        self.assertAlmostEqual(t["daily_totals"]["cost_yuan"], self.price @ np.arange(144.))
        self.assertTrue(t["table2"][-1]["end"].startswith("2026-01-01T00:00"))
        self.assertIn("20:00–24:00", render_q1_tables_markdown(t))

    def test_four_hour_partition_at_boundaries(self):
        result = copy.deepcopy(self.result)
        s = result.schedule
        s["C"][:] = 0
        s["D"][:] = 0
        for a in (23, 47, 71, 95, 119):
            s["C"][a], s["D"][a+1] = 10, 8.1
        s["G"] = self.model.load + s["C"] - s["D"]
        s["E"] = np.r_[6000, 6000 + np.cumsum(.9*s["C"] - s["D"]/.9)]
        result.objective_yuan = float(self.price @ s["G"])
        result.status = "feasible"
        t = self.extract(result, strategy="rule")
        self.assertEqual([r["charge_bus_kwh"] for r in t["table2"]], [10]*5+[0])
        np.testing.assert_allclose([r["discharge_bus_kwh"] for r in t["table2"]], [0]+[8.1]*5)
        self.assertAlmostEqual(sum(r["discharge_bus_kwh"] for r in t["table2"]), t["daily_totals"]["discharge_bus_kwh"])
        self.assertAlmostEqual(t["daily_totals"]["terminal_energy_kwh"], 6000)

    def test_all_three_real_solver_results_and_no_mutation(self):
        for name, result in self.report["strategies"].items():
            before = copy.deepcopy(result.schedule)
            t = self.extract(result, strategy=name)
            self.assertTrue(t["validation"]["passed"])
            for key in before:
                np.testing.assert_array_equal(before[key], result.schedule[key])

    def test_reject_cached_pass_after_schedule_mutation(self):
        self.result.schedule["G"][0] += 1
        self.assertTrue(self.result.diagnostics["passed"])
        with self.assertRaises(ValueError): self.extract()

    def test_reject_changed_cost_and_nonfinite_schedule(self):
        for mutation in ("cost", "nan", "shape", "status"):
            r = copy.deepcopy(self.result)
            if mutation == "cost": r.objective_yuan += 1
            if mutation == "nan":
                r.schedule["E"] = r.schedule["E"].astype(float)
                r.schedule["E"][10] = np.nan
            if mutation == "shape": r.schedule["G"] = r.schedule["G"][:-1]
            if mutation == "status": r.status = "infeasible"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.extract(r)

    def test_reject_shift_gap_naive_and_short_axis(self):
        b = self.contract.boundaries
        bad = [tuple(x+timedelta(minutes=10) for x in b),
               b[:50]+(b[49],)+b[51:], tuple(x.replace(tzinfo=None) for x in b), b[:-1]]
        for boundaries in bad:
            with self.subTest(boundaries=boundaries[:1]), self.assertRaises(ValueError):
                self.extract(contract=replace(self.contract, boundaries=boundaries))

    def test_reject_unaccepted_or_mismatched_provenance(self):
        for contract in (replace(self.contract, status="candidate"), replace(self.contract, mapping_version="wrong")):
            with self.assertRaises(ValueError): self.extract(contract=contract)
        self.result.metadata["input_kind"] = "standardized"
        with self.assertRaises(ValueError): self.extract()
        self.assertEqual(self.extract(contract=replace(self.contract, status="accepted"))["time_contract_status"], "accepted")
        del self.result.metadata["data_version"]
        with self.assertRaises(ValueError): self.extract(contract=replace(self.contract, status="accepted"))


if __name__ == "__main__":
    unittest.main()
