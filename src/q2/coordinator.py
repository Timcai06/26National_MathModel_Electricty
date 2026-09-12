"""Continuous synthetic day-ahead backtest with explicit warmup and state carry."""
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
import numpy as np

from src.core.model import vector
from .forecast import check_time, history_as_of, midnight, predict_day, validate_days
from .dispatch import plan_from_forecast
from .execution import CausalExecutor, OBSERVATION_POLICY


@dataclass(frozen=True)
class PriceDay:
    day: date
    price_yuan_per_kwh: object
    available_at: datetime

    def __post_init__(self):
        midnight(self.day)
        check_time(self.available_at)
        object.__setattr__(self, 'price_yuan_per_kwh', vector(self.price_yuan_per_kwh, 'daily price', 144))


def compare_multiday(days, prices, *, simulation_start, evaluation_start, end_day,
                     initial_energy_kwh, initial_state_source, battery_params,
                     terminal_policy, emergency_multiplier, observation_policy, metadata):
    """No skipped dates, state resets, automatic fallback, or future-actual planning.

    The harness alone holds evaluation truth and releases one slot at a time.
    Whole-day archival availability governs future prediction access separately.
    """
    actuals = validate_days(days)
    if not (midnight(simulation_start) <= midnight(evaluation_start) <= midnight(end_day)):
        raise ValueError('Require simulation_start <= evaluation_start <= end_day')
    if terminal_policy not in {'daily_neutral', 'cross_day_free', 'cross_day_restore'}:
        raise ValueError('Explicit supported terminal policy required')
    if observation_policy != OBSERVATION_POLICY:
        raise ValueError('Explicit observation assumption required')
    required = ['input_kind','data_version','mapping_version','assumptions_version']
    if not isinstance(metadata, dict) or any(not isinstance(metadata.get(k),str) or not metadata[k].strip() for k in required):
        raise ValueError('Versioned provenance required')
    if metadata['input_kind'] != 'synthetic':
        raise ValueError('This harness accepts synthetic observations only pending real slot-availability contract')
    if not isinstance(initial_state_source,str) or not initial_state_source.strip():
        raise ValueError('Initial state source must be explicit')
    prices = tuple(prices)
    if any(not isinstance(p,PriceDay) for p in prices) or any(a.day >= b.day for a,b in zip(prices,prices[1:])):
        raise ValueError('Price days must be unique and ordered')
    truth, price_map = {d.day:d for d in actuals}, {p.day:p for p in prices}
    targets = [simulation_start+timedelta(days=i) for i in range((end_day-simulation_start).days+1)]
    if any(d not in truth or d not in price_map for d in targets):
        raise ValueError('Missing actual or price day; no skipping')
    if any(price_map[d].available_at > midnight(d) for d in targets):
        raise ValueError('Day-ahead price published after decision cutoff')
    config = dict(simulation_start=str(simulation_start),evaluation_start=str(evaluation_start),end_day=str(end_day),
        initial_energy_kwh=initial_energy_kwh,initial_state_source=initial_state_source,
        terminal_policy=terminal_policy,emergency_multiplier=emergency_multiplier,
        observation_policy=observation_policy,battery_params=asdict(battery_params))
    strategies = {}
    for method in ['yesterday','last_week']:
        energy = initial_energy_kwh
        daily = []
        failure = None
        for day in targets:
            history = history_as_of(actuals,midnight(day))
            forecast = predict_day(history,target_day=day,method=method)
            if forecast.status != 'ready':
                failure = {'day':str(day),'stage':'forecast','reason':forecast.status}
                break
            target = energy if terminal_policy == 'daily_neutral' else (
                initial_energy_kwh if terminal_policy == 'cross_day_restore' and day == end_day else None)
            price = price_map[day]
            plan = plan_from_forecast(forecast,price_yuan_per_kwh=price.price_yuan_per_kwh,
                price_available_at=price.available_at,battery_params=battery_params,
                initial_energy_kwh=energy,terminal_energy_kwh=target)
            if plan.status != 'optimal' or not plan.diagnostics.get('passed') or plan.schedule is None:
                failure = {'day':str(day),'stage':'planning','reason':plan.status}
                break
            executor = CausalExecutor(day=day,commitment_kwh=plan.schedule['G'],
                price_yuan_per_kwh=price.price_yuan_per_kwh,price_available_at=price.available_at,
                battery_params=battery_params,initial_energy_kwh=energy,terminal_energy_kwh=target,
                emergency_multiplier=emergency_multiplier,observation_policy=observation_policy)
            observed = truth[day]
            for i in range(144):
                executor.step(slot_id=i,load_kwh=float(observed.load_kwh[i]),pv_kwh=float(observed.pv_kwh[i]),
                              available_at=midnight(day)+timedelta(minutes=10*(i+1)))
            execution = executor.finish()
            if execution['status'] != 'validated':
                failure = {'day':str(day),'stage':'execution','reason':execution['status']}
                break
            daily.append({'day':str(day),'period':'warmup' if day < evaluation_start else 'evaluation',
                'forecast':asdict(forecast),'planned_cost_yuan':plan.objective_yuan,
                'planning_backend':plan.backend,'planning_diagnostics':plan.diagnostics,
                'initial_energy_kwh':energy,'terminal_energy_kwh':executor.energy_kwh,'execution':execution})
            energy = executor.energy_kwh  # Carry actual state, never the forecast terminal state.
        result = {'status':'complete' if failure is None else 'blocked','failure':failure,'daily':daily,'summary':None}
        if failure is None:
            evaluation = [d for d in daily if d['period']=='evaluation']
            def costs(period):
                rows = [d for d in daily if d['period']==period]
                return {key:sum(d['execution']['costs'][key] for d in rows)
                        for key in ['normal_purchase_yuan','emergency_purchase_yuan','total_yuan']}
            result['summary'] = {'evaluation_days':len(evaluation),'warmup_days':len(daily)-len(evaluation),
                'evaluation_costs':costs('evaluation'),'warmup_costs':costs('warmup'),
                'evaluation_initial_energy_kwh':evaluation[0]['initial_energy_kwh'],
                'final_energy_kwh':energy,'emergency_kwh':sum(sum(d['execution']['schedule']['U']) for d in evaluation),
                'max_cross_day_residual_kwh':max([0.]+[abs(a['terminal_energy_kwh']-b['initial_energy_kwh'])
                                                      for a,b in zip(daily,daily[1:])])}
        strategies[method] = result
    complete = all(r['status']=='complete' for r in strategies.values())
    comparable = False
    if complete:
        a,b = [r['summary'] for r in strategies.values()]
        comparable = all(abs(a[key]-b[key]) < 1e-6 for key in ['evaluation_initial_energy_kwh','final_energy_kwh'])
    return {'status':'complete' if complete else 'incomplete','configuration':config,'metadata':dict(metadata),
        'strategies':strategies,'cost_comparison_valid':comparable,
        'comparison_note':'same dates, policy, and boundary energy' if comparable else
            'Do not rank total costs: incomplete coverage or unequal evaluation boundary energy; no terminal value applied',
        'scope':'synthetic causal simulation under explicit observation/recourse assumptions; no Gate 4 acceptance'}
