"""Annual-scale arithmetic check of the power-to-energy convention.

No solver and no policy: this only measures how much the convention moves the
annual energy totals and the arithmetic no-storage purchase cost. It exists to
tell us whether the single-day Q1 sensitivity is representative at annual scale.

Unlike the single representative day, the annual file has a physically valid
left endpoint for every day except the first: today's 00:00 equals the previous
day's 24:00 sample. That cross-day source is used explicitly here.
"""
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

ANNUAL = ROOT / "data/processed/team_delivery/annual_actual.csv"
PRICE = ROOT / "data/processed/team_delivery/dynamic_price.csv"
OUTPUT = ROOT / "analysis/time_integration_sensitivity_v1"

DAYS, SLOTS = 365, 144


def load_matrix(path, column):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != DAYS * SLOTS:
        raise ValueError(f"{path.name}: expected {DAYS * SLOTS} rows, got {len(rows)}")
    values = np.array([float(r[column]) for r in rows]).reshape(DAYS, SLOTS)
    return values, digest


def right_end(points):
    return points / 6.0


def left_end(points):
    energy = np.empty_like(points)
    energy[:, 1:] = points[:, :-1] / 6.0
    energy[1:, 0] = points[:-1, -1] / 6.0     # today 00:00 = previous day 24:00
    energy[0, 0] = points[0, 0] / 6.0         # 2025-01-01 has no previous day
    return energy


def trapezoid(points):
    energy = np.empty_like(points)
    energy[:, 1:] = (points[:, :-1] + points[:, 1:]) / 12.0
    energy[1:, 0] = (points[:-1, -1] + points[1:, 0]) / 12.0
    energy[0, 0] = points[0, 0] / 6.0
    return energy


def main():
    load_kw, load_digest = load_matrix(ANNUAL, "load_kw")
    pv_kw, pv_digest = load_matrix(ANNUAL, "pv_actual_kw")
    price, price_digest = load_matrix(PRICE, "price")

    if not (abs(load_kw / 6 - load_matrix(ANNUAL, "load_kwh")[0]).max() < 1e-8):
        raise ValueError("annual_actual no longer stores the right-end convention")

    conventions = {"right_end": right_end, "left_end": left_end, "trapezoid": trapezoid}
    results = []
    for name, fn in conventions.items():
        load_e, pv_e = fn(load_kw), fn(pv_kw)
        no_storage = float((price * np.maximum(load_e - pv_e, 0.0)).sum())
        results.append({
            "variant": name,
            "annual_load_energy_kwh": float(load_e.sum()),
            "annual_pv_energy_kwh": float(pv_e.sum()),
            "annual_no_storage_cost_yuan": no_storage,
        })

    base = results[0]
    for row in results:
        row["load_energy_delta_percent"] = 100.0 * (
            row["annual_load_energy_kwh"] - base["annual_load_energy_kwh"]) / base["annual_load_energy_kwh"]
        row["pv_energy_delta_percent"] = 100.0 * (
            row["annual_pv_energy_kwh"] - base["annual_pv_energy_kwh"]) / base["annual_pv_energy_kwh"]
        row["no_storage_cost_delta_yuan"] = (
            row["annual_no_storage_cost_yuan"] - base["annual_no_storage_cost_yuan"])
        row["no_storage_cost_delta_percent"] = 100.0 * row["no_storage_cost_delta_yuan"] / base["annual_no_storage_cost_yuan"]

    OUTPUT.mkdir(parents=True, exist_ok=True)
    bundle = {
        "scope": "annual arithmetic check only; no solver, no policy, no result overwritten",
        "day_count": DAYS,
        "slot_count": SLOTS,
        "cross_day_rule": "today 00:00 = previous day 24:00 sample; 2025-01-01 falls back to its own 00:10",
        "source_sha256": {"annual_actual.csv": load_digest, "dynamic_price.csv": price_digest},
        "variants": results,
        "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (OUTPUT / "annual_check.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n")

    print(f"{'variant':14s} {'load GWh':>10s} {'pv GWh':>9s} {'no-storage 元':>14s} {'cost delta':>12s} {'cost %':>9s}")
    for row in results:
        print(f"{row['variant']:14s} {row['annual_load_energy_kwh']/1e6:10.4f} "
              f"{row['annual_pv_energy_kwh']/1e6:9.4f} {row['annual_no_storage_cost_yuan']:14.2f} "
              f"{row['no_storage_cost_delta_yuan']:+12.2f} {row['no_storage_cost_delta_percent']:+8.4f}%")


if __name__ == "__main__":
    main()
