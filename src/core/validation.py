"""Independent physical checks from equations, not the assembled matrix."""

import numpy as np

TOLERANCE = 1e-6


def validate_solution(model, x):
    x = np.asarray(x, dtype=float)
    if x.shape != model.lower.shape or not np.isfinite(x).all():
        return {"passed": False, "reason": "invalid_or_nonfinite_solution"}
    values = {name: x[part] for name, part in model.layout.items()}
    g, c, d, u, w, e = (values[key] for key in ["G", "C", "D", "U", "W", "E"])
    b = model.battery
    cmax, dmax = b.bus_limits(model.dt_hours)
    balance = g + model.pv + d + u - model.load - c - w
    state = np.diff(e) - b.charge_efficiency * c + d / b.discharge_efficiency
    bounds = max(0., -min(g.min(), c.min(), d.min(), u.min(), w.min()),
                 float(c.max() - cmax), float(d.max() - dmax),
                 float(b.min_energy_kwh - e.min()), float(e.max() - b.max_energy_kwh))
    report = {
        "balance_residual_kwh": float(np.max(np.abs(balance))),
        "state_residual_kwh": float(np.max(np.abs(state))),
        "bound_violation_kwh": float(bounds),
        "initial_residual_kwh": float(abs(e[0] - model.initial_energy)),
        "terminal_residual_kwh": 0. if model.terminal_energy is None else float(abs(e[-1] - model.terminal_energy)),
        "commitment_residual_kwh": 0. if model.fixed_purchase is None else float(np.max(np.abs(g - model.fixed_purchase))),
        "disabled_emergency_kwh": 0. if model.emergency_enabled else float(np.max(np.abs(u))),
        "cumulative_state_residual_kwh": float(abs(e[-1] - e[0] - b.charge_efficiency * c.sum() + d.sum() / b.discharge_efficiency)),
    }
    report["simultaneous_slots"] = np.flatnonzero((c > TOLERANCE) & (d > TOLERANCE)).tolist()
    if model.mutual_exclusion:
        z = values["z"]
        report["binary_violation"] = float(max(np.max(np.abs(z - np.round(z))), -z.min(), z.max() - 1, 0))
        report["switch_violation_kwh"] = float(max(np.max(c - cmax * z), np.max(d - dmax * (1 - z)), 0))
    report["physical_passed"] = all(v < TOLERANCE for k, v in report.items() if k != "simultaneous_slots")
    report["passed"] = report["physical_passed"] and not report["simultaneous_slots"]
    return report
