"""Write three-strategy reports using synthetic inputs only, never official XLSX."""

from dataclasses import asdict, is_dataclass
import csv
import hashlib
import json
from pathlib import Path
import platform
import sys

import numpy as np
import scipy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.core import BatteryParams
from src.q1 import compare_q1_strategies


def encode(obj):
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    raise TypeError(f"Unsupported JSON value: {type(obj)}")


def cases():
    load, pv, price = np.zeros(144), np.zeros(144), np.ones(144)
    load[-1], price[0] = 81, .5
    yield "hand_arbitrage", load, pv, price
    yield "flat_no_pv", np.full(144, 20.), np.zeros(144), np.full(144, .5)
    rng = np.random.default_rng(20260911)
    yield "seeded_variable_day", rng.uniform(100, 700, 144), rng.uniform(0, 900, 144), rng.uniform(.2, 1.2, 144)


def main():
    reports, rows = {}, []
    for name, load, pv, price in cases():
        report = compare_q1_strategies(
            load_kwh=load, pv_forecast_kwh=pv, price_yuan_per_kwh=price,
            initial_energy_kwh=6000, battery_params=BatteryParams(.9, .9, "bus"),
            slot_ids=list(range(144)), input_metadata={
                "input_kind": "synthetic", "data_version": name + "-v1",
                "mapping_version": "synthetic-144-v1", "assumptions_version": "0.9-bus-neutral-v1",
            },
        )
        if report["status"] != "passed":
            raise RuntimeError(f"{name} comparison failed: {report.get('failed_strategy')}")
        report["input"] = {"load_kwh": load, "pv_forecast_kwh": pv, "price_yuan_per_kwh": price}
        reports[name] = report
        rows.extend({"case": name, **row} for row in report["summary"])
        print(name + ": " + ", ".join(f"{r['strategy']}={r['cost_yuan']:.6f}" for r in report["summary"]))
    output = ROOT / "analysis/q1_comparison"
    output.mkdir(parents=True, exist_ok=True)
    bundle = {
        "scope": "synthetic-only; no competition results, original-data processing or Gate 2 acceptance",
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "reports": reports,
        "code_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted((ROOT / "src").rglob("*.py"))},
    }
    (output / "comparison.json").write_text(json.dumps(bundle, default=encode, ensure_ascii=False, indent=2) + "\n")
    with (output / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("SYNTHETIC ONLY: analysis/q1_comparison/comparison.json and summary.csv")


if __name__ == "__main__":
    main()
