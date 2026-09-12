"""Build sparse, solver-independent physical equations and variable bounds."""

from dataclasses import dataclass
import math

import numpy as np
from scipy.sparse import lil_matrix


def vector(value, name, size=None):
    result = np.array(value, dtype=float, copy=True)
    if result.ndim != 1 or result.size == 0 or not np.isfinite(result).all():
        raise ValueError(f"{name} must be a finite, nonempty 1-D array")
    if size is not None and result.size != size:
        raise ValueError(f"{name} must have length {size}")
    if (result < 0).any():
        raise ValueError(f"{name} must be nonnegative; values are not repaired")
    result.flags.writeable = False
    return result


@dataclass(frozen=True)
class BatteryParams:
    charge_efficiency: float
    discharge_efficiency: float
    power_reference_side: str
    capacity_kwh: float = 12000
    min_energy_kwh: float = 1200
    max_energy_kwh: float = 10800
    max_charge_kw: float = 5000
    max_discharge_kw: float = 5000

    def __post_init__(self):
        numbers = [v for k, v in vars(self).items() if k != "power_reference_side"]
        if not all(math.isfinite(v) for v in numbers):
            raise ValueError("Battery parameters must be finite")
        if not (0 < self.charge_efficiency <= 1 and 0 < self.discharge_efficiency <= 1):
            raise ValueError("Efficiencies must be in (0, 1]")
        if not (0 <= self.min_energy_kwh <= self.max_energy_kwh <= self.capacity_kwh
                and self.capacity_kwh > 0):
            raise ValueError("Invalid storage capacity/energy bounds")
        if min(self.max_charge_kw, self.max_discharge_kw) < 0:
            raise ValueError("Power limits cannot be negative")
        if self.power_reference_side not in {"bus", "battery"}:
            raise ValueError("power_reference_side must be bus or battery")

    def bus_limits(self, dt_hours):
        charge = self.max_charge_kw * dt_hours
        discharge = self.max_discharge_kw * dt_hours
        if self.power_reference_side == "battery":
            charge /= self.charge_efficiency
            discharge *= self.discharge_efficiency
        return charge, discharge


@dataclass
class PhysicalModel:
    load: np.ndarray
    pv: np.ndarray
    battery: BatteryParams
    initial_energy: float
    terminal_energy: float | None
    dt_hours: float
    emergency_enabled: bool
    fixed_purchase: np.ndarray | None
    mutual_exclusion: bool
    layout: dict
    lower: np.ndarray
    upper: np.ndarray
    a_eq: object
    b_eq: np.ndarray
    a_ub: object
    b_ub: np.ndarray
    integrality: np.ndarray

    @property
    def horizon(self):
        return len(self.load)


def build_microgrid_constraints(*, load_kwh, pv_kwh, battery_params,
                               initial_energy_kwh, terminal_energy_kwh,
                               dt_hours=1 / 6, emergency_enabled=False,
                               fixed_purchase_kwh=None, mutual_exclusion=False):
    load = vector(load_kwh, "load_kwh")
    n = len(load)
    pv = vector(pv_kwh, "pv_kwh", n)
    b = battery_params
    if not isinstance(b, BatteryParams):
        raise ValueError("battery_params must be BatteryParams")
    if not math.isfinite(dt_hours) or dt_hours <= 0:
        raise ValueError("dt_hours must be finite and positive")
    for value in [initial_energy_kwh, terminal_energy_kwh]:
        if value is not None and (not math.isfinite(value) or not b.min_energy_kwh <= value <= b.max_energy_kwh):
            raise ValueError("Initial/terminal energy outside battery bounds")
    if initial_energy_kwh is None:
        raise ValueError("Initial energy must be explicit")
    fixed = None if fixed_purchase_kwh is None else vector(fixed_purchase_kwh, "fixed_purchase_kwh", n)
    layout = {name: slice(i * n, (i + 1) * n) for i, name in enumerate(["G", "C", "D", "U", "W"])}
    layout["E"] = slice(5 * n, 6 * n + 1)
    count = 6 * n + 1
    if mutual_exclusion:
        layout["z"] = slice(count, count + n)
        count += n
    lower, upper = np.zeros(count), np.full(count, np.inf)
    cmax, dmax = b.bus_limits(dt_hours)
    upper[layout["C"]], upper[layout["D"]] = cmax, dmax
    upper[layout["U"]] = np.inf if emergency_enabled else 0
    lower[layout["E"]], upper[layout["E"]] = b.min_energy_kwh, b.max_energy_kwh
    e0 = layout["E"].start
    lower[e0] = upper[e0] = initial_energy_kwh
    if terminal_energy_kwh is not None:
        lower[e0 + n] = upper[e0 + n] = terminal_energy_kwh
    if fixed is not None:
        lower[layout["G"]] = upper[layout["G"]] = fixed
    a_eq = lil_matrix((2 * n, count), dtype=float)
    rhs = np.r_[load - pv, np.zeros(n)]
    for t in range(n):
        for name, coefficient in [("G", 1), ("C", -1), ("D", 1), ("U", 1), ("W", -1)]:
            a_eq[t, layout[name].start + t] = coefficient
        a_eq[n + t, e0 + t] = -1
        a_eq[n + t, e0 + t + 1] = 1
        a_eq[n + t, layout["C"].start + t] = -b.charge_efficiency
        a_eq[n + t, layout["D"].start + t] = 1 / b.discharge_efficiency
    a_ub = lil_matrix((2 * n if mutual_exclusion else 0, count), dtype=float)
    rhs_ub = np.zeros(a_ub.shape[0])
    integrality = np.zeros(count, dtype=int)
    if mutual_exclusion:
        upper[layout["z"]] = 1
        integrality[layout["z"]] = 1
        for t in range(n):
            z = layout["z"].start + t
            a_ub[t, layout["C"].start + t], a_ub[t, z] = 1, -cmax
            a_ub[n + t, layout["D"].start + t], a_ub[n + t, z] = 1, dmax
            rhs_ub[n + t] = dmax
    return PhysicalModel(load, pv, b, initial_energy_kwh, terminal_energy_kwh,
                         dt_hours, emergency_enabled, fixed, mutual_exclusion,
                         layout, lower, upper, a_eq.tocsc(), rhs,
                         a_ub.tocsc(), rhs_ub, integrality)


def with_mutual_exclusion(model):
    return build_microgrid_constraints(
        load_kwh=model.load, pv_kwh=model.pv, battery_params=model.battery,
        initial_energy_kwh=model.initial_energy, terminal_energy_kwh=model.terminal_energy,
        dt_hours=model.dt_hours, emergency_enabled=model.emergency_enabled,
        fixed_purchase_kwh=model.fixed_purchase, mutual_exclusion=True,
    )
