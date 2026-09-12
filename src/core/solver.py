"""HiGHS LP first, with a fresh MILP solve if simultaneous flow is found."""

from dataclasses import dataclass, field
import math
import time

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp

from .model import vector, with_mutual_exclusion
from .validation import TOLERANCE, validate_solution


@dataclass
class SolveResult:
    status: str
    message: str
    backend: str
    objective_yuan: float | None = None
    schedule: dict | None = None
    diagnostics: dict = field(default_factory=dict)
    attempts: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


def _run_backend(model, objective, seconds):
    if model.mutual_exclusion:
        constraints = [LinearConstraint(model.a_eq, model.b_eq, model.b_eq),
                       LinearConstraint(model.a_ub, -np.inf, model.b_ub)]
        return milp(objective, integrality=model.integrality,
                    bounds=Bounds(model.lower, model.upper), constraints=constraints,
                    options={"time_limit": seconds, "mip_rel_gap": 0.0})
    return linprog(objective, A_eq=model.a_eq, b_eq=model.b_eq,
                   bounds=list(zip(model.lower, model.upper)), method="highs",
                   options={"time_limit": seconds, "primal_feasibility_tolerance": 1e-8,
                            "dual_feasibility_tolerance": 1e-8})


def solve_model(model, *, price_yuan_per_kwh, emergency_price_yuan_per_kwh=None,
                mode="auto", time_limit_seconds=30):
    """Only validated optima expose schedules; limits/errors never become zeros.

    A free terminal state is permitted by the physical builder, but selecting its
    economic value is the caller's responsibility. This is not a Q2/Q3 policy.
    """
    prices = vector(price_yuan_per_kwh, "price_yuan_per_kwh", model.horizon)
    if model.emergency_enabled and emergency_price_yuan_per_kwh is None:
        raise ValueError("Emergency purchases require an explicit price vector")
    emergency = (np.zeros(model.horizon) if emergency_price_yuan_per_kwh is None else
                 vector(emergency_price_yuan_per_kwh, "emergency_price_yuan_per_kwh", model.horizon))
    if mode not in {"auto", "lp", "milp"}:
        raise ValueError("mode must be auto, lp or milp")
    if not math.isfinite(time_limit_seconds) or time_limit_seconds <= 0:
        raise ValueError("time_limit_seconds must be positive and finite")
    if model.mutual_exclusion and mode == "lp":
        raise ValueError("Cannot solve an integer model as an LP silently")
    if mode == "milp" and not model.mutual_exclusion:
        model = with_mutual_exclusion(model)
    deadline = time.monotonic() + time_limit_seconds
    attempts = []
    while True:
        backend = "highs_milp" if model.mutual_exclusion else "highs_lp"
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return SolveResult("limit", "Overall time budget exhausted", backend, attempts=attempts)
        objective = np.zeros(len(model.lower))
        objective[model.layout["G"]] = prices
        objective[model.layout["U"]] = emergency
        raw = _run_backend(model, objective, remaining)
        attempts.append({"backend": backend, "status_code": int(raw.status),
                         "message": str(raw.message), "mip_gap": getattr(raw, "mip_gap", None)})
        if raw.status != 0:
            status = {1: "limit", 2: "infeasible", 3: "unbounded"}.get(raw.status, "solver_error")
            return SolveResult(status, str(raw.message), backend, attempts=attempts)
        if raw.x is None:
            return SolveResult("validation_failed", "Optimal status without solution", backend, attempts=attempts)
        diagnostics = validate_solution(model, raw.x)
        if (not model.mutual_exclusion and mode == "auto"
                and diagnostics.get("physical_passed") and diagnostics["simultaneous_slots"]):
            attempts[-1]["fallback_reason"] = "simultaneous_charge_and_discharge"
            attempts[-1]["simultaneous_slots"] = diagnostics["simultaneous_slots"]
            model = with_mutual_exclusion(model)
            continue
        if not diagnostics["passed"]:
            return SolveResult("validation_failed", "Independent physical checks failed", backend,
                               diagnostics=diagnostics, attempts=attempts)
        cost = float(prices @ raw.x[model.layout["G"]] + emergency @ raw.x[model.layout["U"]])
        if raw.fun is None or not np.isfinite(raw.fun) or not np.isfinite(cost) or abs(cost - raw.fun) >= TOLERANCE:
            return SolveResult("validation_failed", "Independent cost check failed", backend, attempts=attempts)
        diagnostics["objective_residual_yuan"] = abs(cost - float(raw.fun))
        # Preserve the actual solve, including small signed numerical errors.
        schedule = {name: raw.x[part].copy() for name, part in model.layout.items() if name != "z"}
        return SolveResult("optimal", str(raw.message), backend, cost, schedule, diagnostics, attempts)
