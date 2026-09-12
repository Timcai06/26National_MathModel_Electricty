"""Fixed, feasible Q1 heuristics without any call to an optimizer."""

from dataclasses import asdict, dataclass
import math

import numpy as np

from src.core.model import vector
from src.core.solver import SolveResult
from src.core.validation import TOLERANCE, validate_solution


@dataclass(frozen=True)
class RuleConfig:
    low_price_fraction: float = .25
    high_price_fraction: float = .75

    def __post_init__(self):
        if not (math.isfinite(self.low_price_fraction) and math.isfinite(self.high_price_fraction)
                and 0 <= self.low_price_fraction < self.high_price_fraction <= 1):
            raise ValueError("Rule price fractions must satisfy 0 <= low < high <= 1")


def _check_model(model):
    if (model.terminal_energy != model.initial_energy or model.emergency_enabled
            or model.fixed_purchase is not None or model.mutual_exclusion):
        raise ValueError("Baselines require a daily-neutral Q1 continuous physical model")


def _finish(model, price, schedule, name, metadata):
    x = np.zeros(len(model.lower))
    for key, values in schedule.items():
        x[model.layout[key]] = values
    checks = validate_solution(model, x)
    if not checks["passed"]:
        return SolveResult("validation_failed", "Baseline physical checks failed", name,
                           diagnostics=checks, metadata=metadata)
    cost = float(price @ schedule["G"])
    if not math.isfinite(cost):
        return SolveResult("validation_failed", "Nonfinite baseline cost", name, metadata=metadata)
    return SolveResult("feasible", "Feasible heuristic; no optimality claim", name,
                       cost, schedule, checks, metadata=metadata)


def no_storage_baseline(model, *, price_yuan_per_kwh):
    _check_model(model)
    price = vector(price_yuan_per_kwh, "price_yuan_per_kwh", model.horizon)
    n = model.horizon
    schedule = {"G": np.maximum(model.load - model.pv, 0),
                "W": np.maximum(model.pv - model.load, 0),
                "C": np.zeros(n), "D": np.zeros(n), "U": np.zeros(n),
                "E": np.full(n + 1, model.initial_energy)}
    return _finish(model, price, schedule, "no_storage", {"policy_version": "no-storage-v1"})


def rule_baseline(model, *, price_yuan_per_kwh, config=RuleConfig()):
    """PV-first, range-based price thresholds, protected initial energy.

    All future values used here are the already-given Q1 forecasts/prices.
    This is not a causal policy for Q2 and must not be given future actuals.
    """
    _check_model(model)
    price = vector(price_yuan_per_kwh, "price_yuan_per_kwh", model.horizon)
    b, n, target = model.battery, model.horizon, model.initial_energy
    cmax, dmax = b.bus_limits(model.dt_hours)
    q = b.charge_efficiency * b.discharge_efficiency
    pmin, pmax = float(price.min()), float(price.max())
    low = pmin + config.low_price_fraction * (pmax - pmin)
    high = pmin + config.high_price_fraction * (pmax - pmin)
    deficit = np.maximum(model.load - model.pv, 0)
    surplus = np.maximum(model.pv - model.load, 0)
    s = {key: np.zeros(n) for key in ["G", "C", "D", "U", "W"]}
    s["E"] = np.zeros(n + 1)
    s["E"][0] = target
    forced_slots = []
    for t in range(n):
        energy = s["E"][t]
        available = max(0., (energy - target) * b.discharge_efficiency)
        desired = energy
        if surplus[t] > 0:
            future_need = float(np.minimum(deficit[t + 1:], dmax).sum())
            charge = min(surplus[t], cmax, max(0., future_need - available) / q)
            desired += b.charge_efficiency * charge
        elif deficit[t] > 0 and price[t] >= high:
            discharge = min(deficit[t], dmax, available)
            desired -= discharge / b.discharge_efficiency
        elif pmax > pmin and price[t] <= low:
            eligible = (price[t + 1:] >= high) & (q * price[t + 1:] > price[t])
            future_need = float(np.minimum(deficit[t + 1:], dmax)[eligible].sum())
            charge = min(cmax, max(0., future_need - available) / q)
            desired += b.charge_efficiency * charge

        # Intersection of current-step reachability, equipment limits and the
        # remaining discharge capacity needed to return to target at day end.
        remaining = n - t - 1
        lower = max(target, energy - dmax / b.discharge_efficiency)
        upper = min(b.max_energy_kwh, energy + b.charge_efficiency * cmax,
                    target + remaining * dmax / b.discharge_efficiency)
        if lower > upper + TOLERANCE:
            raise RuntimeError("Rule terminal reachability invariant was violated")
        next_energy = max(lower, min(upper, desired))
        if next_energy < desired - TOLERANCE:
            forced_slots.append(t)
        if next_energy >= energy:
            s["C"][t] = (next_energy - energy) / b.charge_efficiency
        else:
            s["D"][t] = (energy - next_energy) * b.discharge_efficiency
        # State is recomputed from actual actions, never overwritten at midnight.
        s["E"][t + 1] = energy + b.charge_efficiency * s["C"][t] - s["D"][t] / b.discharge_efficiency
        net = model.load[t] + s["C"][t] - model.pv[t] - s["D"][t]
        s["G"][t], s["W"][t] = max(net, 0.), max(-net, 0.)
    return _finish(model, price, s, "rule", {
        "policy_version": "pv-first-protected-reserve-v1", "config": asdict(config),
        "low_price_yuan_per_kwh": low, "high_price_yuan_per_kwh": high,
        "protected_reserve_kwh": target, "clipped_preference_slots": forced_slots,
        "uses_q1_given_future_forecasts": True,
    })
