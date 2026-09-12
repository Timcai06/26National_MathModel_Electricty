"""Q1 sensitivity to the power-to-energy integration convention.

Scope: this script ONLY changes how the 144 sampled power points are converted
into 144 interval energies. The physical model, efficiencies, terminal policy,
battery bounds and solver are reused unchanged from the frozen implementation.

It does not modify any existing result file, and it is not a Gate 2 acceptance.
"""
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from src.core import BatteryParams
from src.q1.compare import compare_q1_strategies

SOURCE = ROOT / "data/processed/team_delivery/day_base.csv"
AUDIT = ROOT / "analysis/team_delivery/intake_audit.json"
REFERENCE = ROOT / "analysis/real_q1_candidate/summary.csv"
OUTPUT = ROOT / "analysis/time_integration_sensitivity_v1"

N = 144


def load_points():
    """Read the raw sampled kW points and prices, with the intake hash guard."""
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    audit = json.loads(AUDIT.read_text())
    if audit["input_sha256"].get(str(SOURCE.relative_to(ROOT))) != digest:
        raise ValueError("CSV changed since intake audit")
    if audit["source_comparisons"]["day_base"]["mismatches_above_1e-8"] != 0:
        raise ValueError("Source comparison failed")
    with SOURCE.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != N or [int(r["slot"]) for r in rows] != list(range(N)):
        raise ValueError("Invalid slot order; no sorting or cleaning")
    for index, row in enumerate(rows):
        if abs(float(row["load_kw"]) / 6 - float(row["load_kwh"])) > 1e-8:
            raise ValueError("day_base no longer stores the right-end convention")
        if abs(float(row["pv_forecast_kw"]) / 6 - float(row["pv_forecast_kwh"])) > 1e-8:
            raise ValueError("day_base no longer stores the right-end convention")
    load_kw = np.array([float(r["load_kw"]) for r in rows])
    pv_kw = np.array([float(r["pv_forecast_kw"]) for r in rows])
    price = np.array([float(r["price"]) for r in rows])
    return load_kw, pv_kw, price, digest


def to_energy_right_end(points):
    """E_k = P_k / 6. Each sample is the right endpoint of its own interval."""
    return points / 6.0


def to_energy_left_end(points):
    """E_k = P_{k-1} / 6. Needs P_0 (00:00), which the input does not contain."""
    energy = np.empty(N)
    energy[0] = points[0] / 6.0          # explicit fallback: no 00:00 sample exists
    energy[1:] = points[:-1] / 6.0
    return energy


def to_energy_trapezoid(points):
    """E_k = (P_{k-1} + P_k) / 12. Needs P_0, same fallback as left-end."""
    energy = np.empty(N)
    energy[0] = points[0] / 6.0          # degenerate trapezoid, declared explicitly
    energy[1:] = (points[:-1] + points[1:]) / 12.0
    return energy


def shift_price_left(price):
    """Full left alignment for price as well; P_0 price falls back to P_1."""
    shifted = np.empty(N)
    shifted[0] = price[0]
    shifted[1:] = price[:-1]
    return shifted


def run_variant(name, note, load_kwh, pv_kwh, price, digest):
    inputs = dict(
        load_kwh=[float(v) for v in load_kwh],
        pv_forecast_kwh=[float(v) for v in pv_kwh],
        price_yuan_per_kwh=[float(v) for v in price],
        slot_ids=list(range(N)),
        initial_energy_kwh=6000,
        battery_params=BatteryParams(0.9, 0.9, "bus"),
        input_metadata=dict(
            input_kind="standardized",
            data_version="sha256:" + digest,
            mapping_version="interval-end-v1",
            assumptions_version="eta0.9-each-bus-neutral6000-candidate-v1",
        ),
    )
    comparison = compare_q1_strategies(**inputs)
    if comparison["status"] != "passed":
        raise RuntimeError(f"{name}: comparison failed ({comparison.get('failed_strategy')})")
    rows = {row["strategy"]: row for row in comparison["summary"]}
    independent_no_storage = float(price @ np.maximum(load_kwh - pv_kwh, 0))
    residual = abs(independent_no_storage - rows["no_storage"]["cost_yuan"])
    if residual > 1e-6:
        raise RuntimeError(f"{name}: independent no-storage cost mismatch {residual}")
    return {
        "variant": name,
        "note": note,
        "cost_no_storage_yuan": rows["no_storage"]["cost_yuan"],
        "cost_rule_yuan": rows["rule"]["cost_yuan"],
        "cost_optimized_yuan": rows["optimized"]["cost_yuan"],
        "purchase_kwh_optimized": rows["optimized"]["purchase_kwh"],
        "charge_bus_kwh_optimized": rows["optimized"]["charge_bus_kwh"],
        "discharge_bus_kwh_optimized": rows["optimized"]["discharge_bus_kwh"],
        "saving_fraction_vs_no_storage": rows["optimized"]["saving_fraction_vs_no_storage"],
        "terminal_energy_kwh": rows["optimized"]["terminal_energy_kwh"],
        "independent_no_storage_residual_yuan": residual,
        "status": rows["optimized"]["status"],
    }


def main():
    load_kw, pv_kw, price, digest = load_points()
    total_energy_right = float(load_kw.sum() / 6)
    print(f"right-end total load energy: {total_energy_right:.6f} kWh")

    variants = [
        ("right_end", "current candidate: E_k = P_k/6, price at same index",
         to_energy_right_end(load_kw), to_energy_right_end(pv_kw), price),
        ("left_end", "E_k = P_(k-1)/6; first interval falls back to P_1/6",
         to_energy_left_end(load_kw), to_energy_left_end(pv_kw), price),
        ("trapezoid", "E_k = (P_(k-1)+P_k)/12; first interval degenerate",
         to_energy_trapezoid(load_kw), to_energy_trapezoid(pv_kw), price),
        ("left_end_price_aligned", "left-end energy AND left-shifted price",
         to_energy_left_end(load_kw), to_energy_left_end(pv_kw), shift_price_left(price)),
        ("trapezoid_price_aligned", "trapezoid energy AND left-shifted price",
         to_energy_trapezoid(load_kw), to_energy_trapezoid(pv_kw), shift_price_left(price)),
    ]

    results = [run_variant(name, note, load, pv, p, digest)
               for name, note, load, pv, p in variants]

    reference = {}
    with REFERENCE.open(newline="") as handle:
        for row in csv.DictReader(handle):
            reference[row["strategy"]] = float(row["cost_yuan"])
    reproduced = abs(results[0]["cost_optimized_yuan"] - reference["optimized"])
    if reproduced > 1e-6:
        raise RuntimeError(f"right-end variant does not reproduce the frozen candidate: {reproduced}")

    base = results[0]["cost_optimized_yuan"]
    for row in results:
        row["delta_vs_right_end_yuan"] = row["cost_optimized_yuan"] - base
        row["delta_vs_right_end_percent"] = 100.0 * (row["cost_optimized_yuan"] - base) / base

    OUTPUT.mkdir(parents=True, exist_ok=True)
    bundle = {
        "scope": "Q1 sensitivity to power-to-energy integration convention only; "
                 "not Gate 2 acceptance, no existing result overwritten",
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": digest,
        "reference_optimized_cost_yuan": reference["optimized"],
        "right_end_reproduction_residual_yuan": reproduced,
        "fallback_declared": "input has no 00:00 sample; first interval uses P_1 under "
                             "left-end and trapezoid conventions",
        "variants": results,
        "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (OUTPUT / "result.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n")
    with (OUTPUT / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)

    for row in results:
        print(f"{row['variant']:26s} optimized={row['cost_optimized_yuan']:12.4f} "
              f"delta={row['delta_vs_right_end_yuan']:+10.4f} "
              f"({row['delta_vs_right_end_percent']:+.4f}%)")
    print(f"\nright-end reproduces frozen candidate within {reproduced:.3e} yuan")


if __name__ == "__main__":
    main()
