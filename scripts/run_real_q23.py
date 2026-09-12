"""Reproducible Q2/Q3 candidate annual execution; immutable inputs, explicit assumptions."""
import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from src.core import BatteryParams
from src.core.model import build_microgrid_constraints
from src.core.solver import solve_model
from src.q2.forecast import midnight
from src.q2.execution import CausalExecutor, OBSERVATION_POLICY
from src.q3.pv import parse_forecasts
from src.q3.planning import replan, adjustment_cost
from scripts.run_real_q2_forecast import load_rows, parse_days

OUT = ROOT/'analysis/real_q23_candidate'
BATTERY = BatteryParams(.9, .9, 'bus')


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
        default=lambda v: v.tolist() if isinstance(v, np.ndarray) else str(v))+'\n')


def audited_csv(relative):
    path = ROOT/relative
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    audit = json.loads((ROOT/'analysis/team_delivery/intake_audit.json').read_text())
    if audit['input_sha256'].get(relative) != digest:
        raise ValueError('Source changed since audit: '+relative)
    with path.open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f)), digest


def select_january(days):
    scores, chosen = {}, {}
    for field in ('load', 'pv'):
        scores[field] = {}
        for method, lag in [('yesterday', 1), ('last_week', 7)]:
            residual = np.concatenate([getattr(days[i-lag], field+'_kwh')-
                getattr(days[i], field+'_kwh') for i in range(7, 31)])
            scores[field][method] = float(np.abs(residual).mean())
        chosen[field] = min(scores[field], key=scores[field].get)
    return {'training_start': '2025-01-08', 'training_end': '2025-01-31',
            'selection_available_at': '2025-02-01T00:00:00+08:00',
            'metric': 'MAE kWh/slot; no February-December tuning', 'scores': scores, 'chosen': chosen}


def forecast_actual_history(days, index, chosen):
    arrays, sources = {}, {}
    for field in ('load', 'pv'):
        lag = {'yesterday': 1, 'last_week': 7}[chosen[field]]
        source = days[index-lag]
        if index-lag < 0 or source.available_at > midnight(days[index].day):
            raise ValueError('Unavailable historical forecast source')
        arrays[field] = getattr(source, field+'_kwh')
        sources[field] = {'source_day': str(source.day), 'available_at': source.available_at.isoformat()}
    return arrays, sources


def execute_day(actual, price, energy, prediction, sources, *, published=None,
                update_hours=(), conversion='linear', refund=True, startup=False, fresh_updates=True):
    issue = midnight(actual.day)
    pv = prediction['pv'] if published is None else published[issue].energy(decision_time=issue, method=conversion)
    if startup:
        planned = np.zeros(144)
        plan_check = {'startup': 'zero commitment; no historical forecast; causal emergency recourse'}
    else:
        model = build_microgrid_constraints(load_kwh=prediction['load'], pv_kwh=pv,
            battery_params=BATTERY, initial_energy_kwh=energy, terminal_energy_kwh=6000)
        solution = solve_model(model, price_yuan_per_kwh=price)
        if solution.status != 'optimal' or not solution.diagnostics['passed']:
            raise RuntimeError('Day-ahead solve failed: '+solution.status)
        planned, plan_check = solution.schedule['G'], solution.diagnostics
    current = planned.copy()
    executor = CausalExecutor(day=actual.day, commitment_kwh=current, price_yuan_per_kwh=price,
        price_available_at=issue, battery_params=BATTERY, initial_energy_kwh=energy,
        terminal_energy_kwh=6000, emergency_multiplier=5, observation_policy=OBSERVATION_POLICY)
    revisions = []
    for slot in range(144):
        hour = slot//6
        if slot % 36 == 0 and hour in update_hours:
            decision = issue+timedelta(hours=hour)
            remaining_pv = (published[decision].energy(decision_time=decision, method=conversion)[:144-slot]
                            if fresh_updates else pv[slot:])
            old = current[slot:].copy()
            result = replan(load_kwh=prediction['load'][slot:], pv_kwh=remaining_pv,
                old_commitment=old, price=price[slot:], initial_energy=executor.energy_kwh,
                battery=BATTERY, refund=refund)
            current[slot:] = result['G']
            delta = executor.revise_commitment(commitment_kwh=current, issue_time=decision)
            cost = adjustment_cost(old, current[slot:], price[slot:], refund=refund)
            revisions.append({'issue_time': decision.isoformat(), 'first_slot': slot,
                'initial_energy_kwh': executor.energy_kwh, 'old_remaining_kwh': old.tolist(),
                'new_remaining_kwh': current[slot:].tolist(), 'incremental_cost_yuan': cost,
                'increase_kwh': sum(delta['increase_kwh']), 'decrease_kwh': sum(delta['decrease_kwh']),
                'diagnostics': result['diagnostics'], 'objective_residual_yuan': result['objective_residual_yuan']})
        executor.step(slot_id=slot, load_kwh=float(actual.load_kwh[slot]), pv_kwh=float(actual.pv_kwh[slot]),
            available_at=issue+timedelta(minutes=10*(slot+1)))
    execution = executor.finish()
    if execution['status'] != 'validated':
        raise RuntimeError('Actual execution failed physical checks')
    base = float(price @ planned)
    adjustment = sum(r['incremental_cost_yuan'] for r in revisions)
    emergency = execution['costs']['emergency_purchase_yuan']
    # Independently reconcile original and final purchase ledgers.
    penalty = sum(float(price[r['first_slot']:] @ (
        .5*np.maximum(np.asarray(r['new_remaining_kwh'])-r['old_remaining_kwh'], 0)+
        (.5 if refund else 1.5)*np.maximum(np.asarray(r['old_remaining_kwh'])-r['new_remaining_kwh'], 0))) for r in revisions)
    ledger_residual = abs(base+adjustment-float(price @ current)-penalty)
    if ledger_residual > 1e-6:
        raise RuntimeError('Independent contract ledger failed')
    return {'day': str(actual.day), 'initial_energy_kwh': energy, 'terminal_energy_kwh': executor.energy_kwh,
        'forecast_sources': sources, 'pv_issue_time': issue.isoformat() if published else None,
        'planned_G': planned.tolist(), 'schedule': execution['schedule'], 'revisions': revisions,
        'costs': {'planned_yuan': base, 'adjustment_yuan': adjustment, 'emergency_yuan': emergency,
                  'total_yuan': base+adjustment+emergency},
        'diagnostics': execution['diagnostics'], 'planning_diagnostics': plan_check,
        'ledger_residual_yuan': ledger_residual}


def convert_pv(published):
    directory = ROOT/'data/derived'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory/'pv_10min_candidate.csv'
    with path.open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['issue_time', 'forecast_slot', 'physical_start', 'physical_end', 'linear_kwh', 'step_kwh'])
        for issue, forecast in published.items():
            linear, step = [forecast.energy(decision_time=issue, method=m) for m in ('linear', 'step')]
            for i in range(144):
                writer.writerow([issue.isoformat(), i, (issue+timedelta(minutes=10*i)).isoformat(),
                    (issue+timedelta(minutes=10*(i+1))).isoformat(), linear[i], step[i]])
    return {'path': str(path.relative_to(ROOT)), 'rows': len(published)*144,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'methods': ['piecewise-linear exact interval integral', 'right-hour piecewise constant'],
            'first_hour': 'hold first published forecast; no observed h=0 value', 'semantic_acceptance': False}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows, source, digest = load_rows()
    days = parse_days(rows, delay_minutes=0)
    price_rows, price_hash = audited_csv('data/processed/team_delivery/day_base.csv')
    price = np.array([float(r['price']) for r in price_rows])
    forecast_rows, forecast_hash = audited_csv('data/processed/team_delivery/pv_forecast.csv')
    published = parse_forecasts(forecast_rows)
    conversion = convert_pv(published)
    selection = select_january(days)
    dump(OUT/'january_selection.json', selection)
    print('January-only selection:', selection['chosen'], flush=True)
    # Common physically executed January startup; no future-based training in warmup.
    energy, warmup_cost = 6000., 0.
    with (OUT/'january_warmup.jsonl').open('w') as f:
        for i in range(31):
            prediction, sources = ({'load': np.zeros(144), 'pv': np.zeros(144)}, {}) if i == 0 else forecast_actual_history(days, i, {'load': 'yesterday', 'pv': 'yesterday'})
            result = execute_day(days[i], price, energy, prediction, sources, startup=i == 0)
            energy = result['terminal_energy_kwh']
            warmup_cost += result['costs']['total_yuan']
            f.write(json.dumps(result)+'\n')
    definitions = [
        ('q2_yesterday', {'load': 'yesterday', 'pv': 'yesterday'}, None, (), 'linear', True),
        ('q2_last_week', {'load': 'last_week', 'pv': 'last_week'}, None, (), 'linear', True),
        ('q2_main', selection['chosen'], None, (), 'linear', True),
        ('q3_zero_only', selection['chosen'], published, (), 'linear', True),
        ('q3_update_6', selection['chosen'], published, (6,), 'linear', True),
        ('q3_update_12', selection['chosen'], published, (12,), 'linear', True),
        ('q3_update_18', selection['chosen'], published, (18,), 'linear', True),
        ('q3_main', selection['chosen'], published, (6, 12, 18), 'linear', True),
        ('q3_step', selection['chosen'], published, (6, 12, 18), 'step', True),
        ('q3_no_refund', selection['chosen'], published, (6, 12, 18), 'linear', False),
        ('q3_stale_updates', selection['chosen'], published, (6, 12, 18), 'linear', True)]
    summaries = {}
    for name, chosen, forecasts, updates, method, refund in definitions:
        state = energy
        totals = {key: 0. for key in ['planned_yuan', 'adjustment_yuan', 'emergency_yuan', 'total_yuan']}
        max_residual, emergency_kwh, revision_count, selected = 0., 0., 0, {}
        with (OUT/f'{name}.jsonl').open('w') as f:
            for i in range(31, 365):
                prediction, sources = forecast_actual_history(days, i, chosen)
                result = execute_day(days[i], price, state, prediction, sources,
                    published=forecasts, update_hours=updates, conversion=method, refund=refund,
                    fresh_updates=name != 'q3_stale_updates')
                max_residual = max(max_residual, abs(state-result['initial_energy_kwh']), result['ledger_residual_yuan'])
                state = result['terminal_energy_kwh']
                for key in totals:
                    totals[key] += result['costs'][key]
                emergency_kwh += sum(result['schedule']['U'])
                revision_count += len(result['revisions'])
                if result['day'] in ['2025-03-20', '2025-06-21', '2025-09-23', '2025-12-21']:
                    selected[result['day']] = result
                f.write(json.dumps(result)+'\n')
                if (i-30) % 100 == 0:
                    print(name, i-30, '/334 days', flush=True)
        summaries[name] = {'days': 334, 'costs': totals, 'emergency_kwh': emergency_kwh,
            'updates': revision_count, 'initial_energy_kwh': energy, 'final_energy_kwh': state,
            'max_continuity_or_ledger_residual': max_residual, 'history_methods': chosen,
            'update_hours': updates, 'conversion': method, 'refund_cancelled_original_price': refund,
            'fresh_pv_updates': name != 'q3_stale_updates',
            'daily_file_sha256': hashlib.sha256((OUT/f'{name}.jsonl').read_bytes()).hexdigest()}
        if name in ('q2_main', 'q3_main'):
            dump(OUT/f'{name}_selected_days.json', selected)
        print(name, totals, flush=True)
    hashes = {str(source.relative_to(ROOT)): digest, 'data/processed/team_delivery/day_base.csv': price_hash,
              'data/processed/team_delivery/pv_forecast.csv': forecast_hash}
    if any(hashlib.sha256((ROOT/p).read_bytes()).hexdigest() != h for p, h in hashes.items()):
        raise RuntimeError('Source changed')
    dump(OUT/'result.json', {'scope': 'real Q2/Q3 candidate strategy execution; not global optimum or final semantic acceptance',
        'semantic_acceptance': False, 'input_sha256': hashes, 'source_unchanged': True,
        'evaluation_start': '2025-02-01', 'evaluation_end': '2025-12-31', 'evaluation_days': 334,
        'warmup': {'start': '2025-01-01', 'end': '2025-01-31', 'days': 31, 'initial_energy_kwh': 6000,
                   'final_energy_kwh': energy, 'cost_yuan': warmup_cost,
                   'policy': 'Jan1 zero commitment; Jan2-31 yesterday baseline; daily target6000'},
        'assumptions': {'availability': 'completed day available at next midnight',
            'observation': OBSERVATION_POLICY, 'terminal': 'daily6000 with actual state carry',
            'efficiency': '.9 each direction', 'power_side': 'bus', 'emergency_multiplier': 5,
            'q3_refund': 'refund original cancelled price plus 50% penalty; relative to current commitment',
            'q3_horizon': 'remaining current day only; future day contracts untouched'},
        'conversion': conversion, 'january_selection': selection, 'strategies': summaries,
        'code_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__).resolve(), ROOT/'scripts/run_real_q2_forecast.py', *sorted((ROOT/'src').rglob('*.py'))]}})


if __name__ == '__main__':
    main()
