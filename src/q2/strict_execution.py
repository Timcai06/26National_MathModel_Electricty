"""Slot-start battery commands, followed by slot-end grid settlement.

The controller never receives an actual-day array. Fixed forecasts are issued at
midnight; actual observations only enter settle(), after a command is locked.
"""
from dataclasses import asdict, dataclass
from datetime import timedelta
import math

import numpy as np

from src.core.model import build_microgrid_constraints, vector
from src.core.solver import solve_model
from src.core.validation import validate_solution
from .execution import SlotExecution
from .forecast import check_time, midnight

POLICY = 'slot_start_command_slot_end_grid_settlement_v1'


@dataclass(frozen=True)
class Command:
    slot: int
    decision_time: str
    block_decision_time: str
    forecast_available_at: str
    latest_observation_end: str | None
    C: float
    D: float


class StrictExecutor:
    def __init__(self, *, day, commitment, price, forecast_load, forecast_pv,
                 forecast_available_at, battery, initial_energy=6000., mode='B0'):
        if mode not in ('B0', 'B1'):
            raise ValueError('Unknown strict controller')
        self.start = midnight(day)
        check_time(forecast_available_at)
        if forecast_available_at > self.start:
            raise ValueError('Frozen forecast must be available at midnight')
        self.forecast_available_at = forecast_available_at
        self.g = vector(commitment, 'commitment', 144)
        self.price = vector(price, 'price', 144)
        self.load = vector(forecast_load, 'forecast_load', 144)
        self.pv = vector(forecast_pv, 'forecast_pv', 144)
        self.battery, self.mode = battery, mode
        build_microgrid_constraints(load_kwh=self.load, pv_kwh=self.pv,
            battery_params=battery, initial_energy_kwh=initial_energy, terminal_energy_kwh=6000.)
        self.initial = self.energy = float(initial_energy)
        self.records, self.commands, self.solves = [], [], []
        self.pending = None
        self.block = None

    def decide(self, decision_time):
        i = len(self.records)
        check_time(decision_time)
        if i >= 144 or self.pending is not None or decision_time != self.start+timedelta(minutes=10*i):
            raise ValueError('Exactly one command required at the next slot start')
        b = self.battery
        if self.mode == 'B0':
            cmax, dmax = b.bus_limits(1/6)
            lower = max(b.min_energy_kwh, self.energy-dmax/b.discharge_efficiency,
                        6000-(143-i)*cmax*b.charge_efficiency)
            upper = min(b.max_energy_kwh, self.energy+cmax*b.charge_efficiency,
                        6000+(143-i)*dmax/b.discharge_efficiency)
            if lower > upper+1e-6:
                raise ValueError('Terminal target unreachable')
            net = self.g[i]+self.pv[i]-self.load[i]
            desired = self.energy+(net*b.charge_efficiency if net >= 0 else net/b.discharge_efficiency)
            target = min(upper, max(lower, desired))
            c, d = max(0., (target-self.energy)/b.charge_efficiency), max(0., (self.energy-target)*b.discharge_efficiency)
            block_time = decision_time
        else:
            if i % 6 == 0:
                model = build_microgrid_constraints(load_kwh=self.load[i:], pv_kwh=self.pv[i:],
                    battery_params=b, initial_energy_kwh=self.energy, terminal_energy_kwh=6000.,
                    emergency_enabled=True, fixed_purchase_kwh=self.g[i:])
                result = solve_model(model, price_yuan_per_kwh=self.price[i:],
                                     emergency_price_yuan_per_kwh=5*self.price[i:])
                if result.status != 'optimal':
                    raise RuntimeError('MPC failed: '+result.status)
                self.block = (result.schedule['C'][:6].copy(), result.schedule['D'][:6].copy())
                self.solves.append({'slot': i, 'decision_time': decision_time.isoformat(),
                    'backend': result.backend, 'diagnostics': result.diagnostics})
            c, d = float(self.block[0][i % 6]), float(self.block[1][i % 6])
            block_time = self.start+timedelta(minutes=10*(i-i % 6))
        next_energy = self.energy+b.charge_efficiency*c-d/b.discharge_efficiency
        cmax, dmax = b.bus_limits(1/6)
        if (min(c, d) < -1e-6 or c > cmax+1e-6 or d > dmax+1e-6 or
                (c > 1e-6 and d > 1e-6) or next_energy < b.min_energy_kwh-1e-6 or
                next_energy > b.max_energy_kwh+1e-6):
            raise ValueError('Invalid precommitted battery command')
        # HiGHS can return a boundary a few ulps outside its exact bound.
        # Project the COMMAND (never overwrite realized SOC), with an explicit
        # sub-tolerance interior guard so the next builder accepts that state.
        guarded = min(b.max_energy_kwh-1e-8, max(b.min_energy_kwh+1e-8, next_energy))
        if guarded != next_energy or min(c, d) < 0:
            if abs(guarded-next_energy) > 1e-6:
                raise ValueError('Command projection exceeds numerical tolerance')
            c = max(0., (guarded-self.energy)/b.charge_efficiency)
            d = max(0., (self.energy-guarded)*b.discharge_efficiency)
        self.pending = Command(i, decision_time.isoformat(), block_time.isoformat(),
            self.forecast_available_at.isoformat(), self.records[-1].end_time if i else None, float(c), float(d))
        self.commands.append(self.pending)
        return self.pending

    def settle(self, *, load_kwh, pv_kwh, available_at):
        check_time(available_at)
        i = len(self.records)
        if self.pending is None or available_at != self.start+timedelta(minutes=10*(i+1)):
            raise ValueError('Observation requires a locked command and exact slot end')
        if any(not math.isfinite(v) or v < 0 for v in (load_kwh, pv_kwh)):
            raise ValueError('Invalid actual observation')
        c, d = self.pending.C, self.pending.D
        deficit = load_kwh+c-self.g[i]-pv_kwh-d
        u, w = max(0., deficit), max(0., -deficit)
        end_energy = self.energy+self.battery.charge_efficiency*c-d/self.battery.discharge_efficiency
        record = SlotExecution(i, available_at.isoformat(), float(load_kwh), float(pv_kwh),
            float(self.g[i]), c, d, float(u), float(w), self.energy, end_energy,
            float(self.price[i]*self.g[i]), float(5*self.price[i]*u))
        self.records.append(record)
        self.energy, self.pending = end_energy, None
        return record

    def finish(self):
        if len(self.records) != 144 or self.pending is not None:
            raise ValueError('Incomplete day')
        schedule = {k: np.array([getattr(r, k) for r in self.records]) for k in ('G', 'C', 'D', 'U', 'W')}
        schedule['E'] = np.array([self.initial]+[r.terminal_energy_kwh for r in self.records])
        model = build_microgrid_constraints(load_kwh=[r.load_kwh for r in self.records],
            pv_kwh=[r.pv_kwh for r in self.records], battery_params=self.battery,
            initial_energy_kwh=self.initial, terminal_energy_kwh=6000.,
            emergency_enabled=True, fixed_purchase_kwh=self.g)
        x = np.zeros(len(model.lower))
        for name, values in schedule.items():
            x[model.layout[name]] = values
        diagnostics = validate_solution(model, x)
        if not diagnostics['passed']:
            raise RuntimeError('Strict execution failed physical validation')
        costs = {'planned_yuan': float(self.price @ self.g), 'adjustment_yuan': 0.,
                 'emergency_yuan': float(5*self.price @ schedule['U'])}
        costs['total_yuan'] = sum(costs.values())
        return {'schedule': {k: v.tolist() for k, v in schedule.items()}, 'costs': costs,
            'diagnostics': diagnostics, 'commands': [asdict(c) for c in self.commands],
            'solves': self.solves, 'policy': POLICY, 'controller': self.mode}
