"""Q1 daily-neutral wrapper. No parsing, cleaning, interpolation or file output."""

import numpy as np

from src.core.model import build_microgrid_constraints, vector
from src.core.solver import solve_model


def prepare_q1_inputs(*, load_kwh, pv_forecast_kwh, price_yuan_per_kwh,
                      initial_energy_kwh, battery_params, slot_ids, input_metadata):
    """Shared validation for all strategies; no data processing or sorting."""
    load = vector(load_kwh, "load_kwh", 144)
    pv = vector(pv_forecast_kwh, "pv_forecast_kwh", 144)
    price = vector(price_yuan_per_kwh, "price_yuan_per_kwh", 144)
    if not np.array_equal(np.asarray(slot_ids), np.arange(144)):
        raise ValueError("Q1 requires ordered slot_ids 0..143; no automatic sorting")
    required = ["input_kind", "data_version", "mapping_version", "assumptions_version"]
    if not isinstance(input_metadata, dict) or any(
        not isinstance(input_metadata.get(k), str) or not input_metadata[k].strip() for k in required
    ):
        raise ValueError("Explicit input kind and data/mapping/assumption versions required")
    if input_metadata["input_kind"] not in {"synthetic", "standardized"}:
        raise ValueError("input_kind must be synthetic or standardized")
    model = build_microgrid_constraints(
        load_kwh=load, pv_kwh=pv, battery_params=battery_params,
        initial_energy_kwh=initial_energy_kwh, terminal_energy_kwh=initial_energy_kwh,
    )
    return model, price, input_metadata.copy()


def solve_q1(*, load_kwh, pv_forecast_kwh, price_yuan_per_kwh,
             initial_energy_kwh, battery_params, slot_ids, input_metadata,
             mode="auto", time_limit_seconds=30):
    model, price, metadata = prepare_q1_inputs(
        load_kwh=load_kwh, pv_forecast_kwh=pv_forecast_kwh,
        price_yuan_per_kwh=price_yuan_per_kwh, initial_energy_kwh=initial_energy_kwh,
        battery_params=battery_params, slot_ids=slot_ids, input_metadata=input_metadata,
    )
    result = solve_model(model, price_yuan_per_kwh=price, mode=mode,
                         time_limit_seconds=time_limit_seconds)
    baseline = float(price @ np.maximum(model.load - model.pv, 0))
    result.metadata = {**metadata, "horizon": 144, "terminal_policy": "daily_neutral",
                       "initial_energy_kwh": initial_energy_kwh,
                       "battery_params": vars(battery_params).copy(),
                       "no_storage_cost_yuan": baseline,
                       "time_semantics_verified_by_solver": False}
    # Metadata tracks an upstream contract; it does not prove its correctness.
    if result.status == "optimal":
        result.metadata["saving_vs_no_storage_yuan"] = baseline - result.objective_yuan
        if result.objective_yuan > baseline + 1e-6:
            result.status = "validation_failed"
            result.message = "Optimal cost exceeds an independently feasible no-storage baseline"
            result.schedule = None
            result.objective_yuan = None
    return result
