"""Causal, slot-local recourse and explicit purchase settlement."""
from dataclasses import asdict, dataclass
from datetime import timedelta
import math
import numpy as np

from src.core.model import build_microgrid_constraints, vector
from src.core.validation import validate_solution
from .forecast import check_time, midnight

OBSERVATION_POLICY = 'current_slot_energy_known_before_settlement'


@dataclass(frozen=True)
class SlotExecution:
    slot_id: int
    end_time: str
    load_kwh: float
    pv_kwh: float
    G: float
    C: float
    D: float
    U: float
    W: float
    initial_energy_kwh: float
    terminal_energy_kwh: float
    normal_cost_yuan: float
    emergency_cost_yuan: float


class CausalExecutor:
    """Surplus-first storage, deficit-first discharge, terminal reachability.

    Only this slot's observation enters step(). No future actual array is held.
    A terminal target may force emergency charging or surplus discharge; this is
    an explicit recourse assumption, not an economically optimal policy.
    """
    def __init__(self, *, day, commitment_kwh, price_yuan_per_kwh,
                 price_available_at, battery_params, initial_energy_kwh,
                 terminal_energy_kwh, emergency_multiplier, observation_policy):
        self.day = day
        self._start = midnight(day)
        check_time(price_available_at)
        if price_available_at > self._start:
            raise ValueError('Day-ahead prices must be available at midnight')
        if observation_policy != OBSERVATION_POLICY:
            raise ValueError('Explicit current-slot observation assumption required')
        if not math.isfinite(emergency_multiplier) or emergency_multiplier < 0:
            raise ValueError('Emergency multiplier must be finite and nonnegative')
        self._g = vector(commitment_kwh, 'commitment', 144)
        self._price = vector(price_yuan_per_kwh, 'price', 144)
        self._battery = battery_params
        # Reuse shared parameter validation, without solving actual future data.
        build_microgrid_constraints(load_kwh=np.zeros(144), pv_kwh=np.zeros(144),
            battery_params=battery_params, initial_energy_kwh=initial_energy_kwh,
            terminal_energy_kwh=terminal_energy_kwh)
        self._initial = float(initial_energy_kwh)
        self._energy = self._initial
        self._target = terminal_energy_kwh
        self._multiplier = float(emergency_multiplier)
        self._records = []
        cmax, dmax = battery_params.bus_limits(1/6)
        if terminal_energy_kwh is not None and not (
            self._initial-144*dmax/battery_params.discharge_efficiency-1e-6 <= terminal_energy_kwh
            <= self._initial+144*cmax*battery_params.charge_efficiency+1e-6):
            raise ValueError('Unreachable terminal target')

    @property
    def energy_kwh(self):
        return self._energy

    @property
    def records(self):
        return tuple(self._records)

    def revise_commitment(self, *, commitment_kwh, issue_time):
        """Q3 may revise only unexecuted slots at the current 6-hour boundary."""
        check_time(issue_time)
        slot = len(self._records)
        if slot not in (36, 72, 108) or issue_time != self._start+timedelta(minutes=10*slot):
            raise ValueError('Revision requires an unexecuted 06/12/18 boundary')
        new = vector(commitment_kwh, 'revised commitment', 144)
        if not np.array_equal(new[:slot], self._g[:slot]):
            raise ValueError('Cannot rewrite executed commitments')
        delta = new-self._g
        self._g = new
        return {'increase_kwh': np.maximum(delta, 0).tolist(),
                'decrease_kwh': np.maximum(-delta, 0).tolist()}

    def step(self, *, slot_id, load_kwh, pv_kwh, available_at):
        i = len(self._records)
        if type(slot_id) is not int or slot_id != i or i >= 144:
            raise ValueError('Slots must execute exactly once in order 0..143')
        end = self._start+timedelta(minutes=10*(i+1))
        check_time(available_at)
        if available_at != end:
            raise ValueError('Current-slot totals must be available at its settlement boundary')
        if any(not math.isfinite(v) or v < 0 for v in [load_kwh,pv_kwh]):
            raise ValueError('Invalid observation; no repair or zero filling')
        b, energy = self._battery, self._energy
        cmax, dmax = b.bus_limits(1/6)
        lower = max(b.min_energy_kwh, energy-dmax/b.discharge_efficiency)
        upper = min(b.max_energy_kwh, energy+cmax*b.charge_efficiency)
        if self._target is not None:
            remaining = 143-i
            lower = max(lower, self._target-remaining*cmax*b.charge_efficiency)
            upper = min(upper, self._target+remaining*dmax/b.discharge_efficiency)
        if lower > upper+1e-6:
            raise ValueError('Terminal target no longer reachable')
        net = float(self._g[i]+pv_kwh-load_kwh)
        desired = energy+(b.charge_efficiency*net if net >= 0 else net/b.discharge_efficiency)
        next_energy = min(upper,max(lower,desired))
        c = max(0.,(next_energy-energy)/b.charge_efficiency)
        d = max(0.,(energy-next_energy)*b.discharge_efficiency)
        deficit = load_kwh+c-self._g[i]-pv_kwh-d
        u,w = max(0.,float(deficit)),max(0.,float(-deficit))
        actual_next = energy+b.charge_efficiency*c-d/b.discharge_efficiency
        record = SlotExecution(i,end.isoformat(),float(load_kwh),float(pv_kwh),float(self._g[i]),
            c,d,u,w,energy,actual_next,float(self._price[i]*self._g[i]),
            float(self._multiplier*self._price[i]*u))
        if not all(math.isfinite(v) for v in [c,d,u,w,actual_next,record.normal_cost_yuan,record.emergency_cost_yuan]):
            raise ValueError('Nonfinite execution result')
        self._records.append(record)
        self._energy = actual_next
        return record

    def finish(self):
        if len(self._records) != 144:
            raise ValueError('Full 144-slot execution required for daily settlement')
        schedule = {key:np.array([getattr(r,key) for r in self._records]) for key in ['G','C','D','U','W']}
        schedule['E'] = np.array([self._initial]+[r.terminal_energy_kwh for r in self._records])
        model = build_microgrid_constraints(
            load_kwh=[r.load_kwh for r in self._records],pv_kwh=[r.pv_kwh for r in self._records],
            battery_params=self._battery,initial_energy_kwh=self._initial,terminal_energy_kwh=self._target,
            emergency_enabled=True,fixed_purchase_kwh=self._g)
        x = np.zeros_like(model.lower)
        for name,values in schedule.items(): x[model.layout[name]] = values
        diagnostics = validate_solution(model,x)
        normal = float(self._price @ schedule['G'])
        emergency = float(self._multiplier*self._price @ schedule['U'])
        diagnostics['settlement_residual_yuan'] = abs(normal+emergency-sum(
            r.normal_cost_yuan+r.emergency_cost_yuan for r in self._records))
        diagnostics['state_continuity_residual_kwh'] = max(abs(a.terminal_energy_kwh-b.initial_energy_kwh)
            for a,b in zip(self._records,self._records[1:]))
        passed = diagnostics['passed'] and diagnostics['settlement_residual_yuan'] < 1e-6 and diagnostics['state_continuity_residual_kwh'] < 1e-6
        return {'status':'validated' if passed else 'validation_failed',
            'schedule':{k:v.tolist() for k,v in schedule.items()}, 'records':[asdict(r) for r in self._records],
            'costs':{'normal_purchase_yuan':normal,'emergency_purchase_yuan':emergency,'total_yuan':normal+emergency},
            'diagnostics':diagnostics,'policy':{'recourse':'greedy_net_balance_with_terminal_reachability',
                'observation':OBSERVATION_POLICY,'emergency_multiplier':self._multiplier,
                'terminal_energy_kwh':self._target,'initial_energy_kwh':self._initial,
                'emergency_charging_for_terminal_allowed':True,'surplus_sale_revenue':0},
            'scope':'causal under stated current-slot observability; no optimality claim'}
