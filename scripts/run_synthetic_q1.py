"""Reproducible Q1 demonstration using synthetic arrays only."""

from dataclasses import asdict
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
from src.q1 import solve_q1


def main():
    load, pv, price = np.zeros(144), np.zeros(144), np.ones(144)
    load[-1], price[0] = 81, .5
    result = solve_q1(
        load_kwh=load, pv_forecast_kwh=pv, price_yuan_per_kwh=price,
        initial_energy_kwh=6000,
        battery_params=BatteryParams(.9, .9, "bus"),
        slot_ids=list(range(144)), input_metadata={
            "input_kind": "synthetic", "data_version": "81kwh-last-slot-v1",
            "mapping_version": "synthetic-ordered-144-v1",
            "assumptions_version": "candidate-0.9-bus-daily-neutral-v1",
        },
    )
    report = {
        "scope": "synthetic verification only; not competition Q1 results or Gate 0 acceptance",
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "input": {"load_kwh": load.tolist(), "pv_kwh": pv.tolist(), "price": price.tolist()},
        "result": asdict(result),
        "code_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted((ROOT / "src").rglob("*.py"))},
    }
    if result.status != "optimal":
        raise RuntimeError(f"Synthetic solve did not pass: {result.status}: {result.message}")
    if abs(result.objective_yuan - 50) > 1e-6:
        raise RuntimeError("Synthetic result disagrees with independent hand calculation")
    target = ROOT / "analysis/synthetic_q1/result.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                default=lambda obj: obj.tolist() if isinstance(obj, np.ndarray) else obj) + "\n")
    print(f"SYNTHETIC ONLY: {result.backend}, cost={result.objective_yuan:.6f}, "
          f"baseline={result.metadata['no_storage_cost_yuan']:.6f}, "
          f"saving={result.metadata['saving_vs_no_storage_yuan']:.6f}")
    print(target.relative_to(ROOT))


if __name__ == "__main__":
    main()
