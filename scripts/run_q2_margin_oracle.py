"""January-frozen residual margins plus same-rule perfect-information bounds."""
from dataclasses import asdict
from pathlib import Path
import csv
import hashlib
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from scripts.run_real_q23 import audited_csv, dump, forecast_actual_history, BATTERY
from scripts.run_real_q2_forecast import load_rows, parse_days
from scripts.run_strict_q2 import execute, OUT as BASE
from src.q2.residual_margin import CANDIDATES, MarginConfig, safety_forecast
from src.q2.oracle import solve_oracle_day
from src.core.model import build_microgrid_constraints
from src.core.solver import solve_model

OUT = ROOT/'analysis/q2_margin_oracle_v1'
METHODS = {'load': 'last_week', 'pv': 'yesterday'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_plan(prediction, price):
    model = build_microgrid_constraints(load_kwh=prediction['load'], pv_kwh=prediction['pv'],
        battery_params=BATTERY, initial_energy_kwh=6000., terminal_energy_kwh=6000.)
    result = solve_model(model, price_yuan_per_kwh=price)
    if result.status != 'optimal':
        raise RuntimeError('Margin day-ahead solve failed: '+result.status)
    return result.schedule['G']


def corrected(days, index, config):
    baseline, sources = forecast_actual_history(days, index, METHODS)
    prediction, audit = safety_forecast(days[:index], target_day=days[index].day,
        baseline_load=baseline['load'], baseline_pv=baseline['pv'], config=config)
    return prediction, sources, audit


def select_config(january, price):
    if len(january) != 31 or any(d.day.month != 1 for d in january):
        raise ValueError('Selection receives January only')
    scores = []
    with (OUT/'january_development.jsonl').open('w') as f:
        for candidate_id, config in enumerate(CANDIDATES):
            total, state = 0., 6000.
            for i in range(14,31):
                prediction, sources, audit = corrected(january, i, config)
                g = make_plan(prediction, price)
                row = execute(january[i], price, prediction, sources, g, state, 'B0')
                state = row['terminal_energy_kwh']
                row.update(candidate_id=candidate_id, margin=audit)
                total += row['costs']['total_yuan']
                f.write(json.dumps(row)+'\n')
            scores.append({'candidate_id': candidate_id, 'config': asdict(config), 'january_total_yuan': total})
    chosen = min(scores, key=lambda s: (s['january_total_yuan'], s['candidate_id']))
    frozen = {'selection': chosen, 'scores': scores, 'scoring_controller': 'B0',
        'parameter_available_at': '2025-02-01T00:00:00+08:00',
        'calibration': 'Jan8-14 first residuals; score Jan15-31 using expanding as-of bank capped at28days',
        'evaluation': 'one retrospective Feb-Dec replay after January freeze; not blind test',
        'methods': METHODS, 'shared_configuration': 'B2 and B3 share B0-selected parameters and daily G',
        'warmup': 'reuse validated B0/B1 January trajectories; enhancement deployed Feb1',
        'development_sha256': sha(OUT/'january_development.jsonl')}
    dump(OUT/'frozen_selection.json', frozen)
    print('Frozen January selection:', chosen, flush=True)
    return MarginConfig(**chosen['config'])


def empty_summary():
    return {'days': 0, 'costs': dict.fromkeys(('planned_yuan','adjustment_yuan','emergency_yuan','total_yuan'), 0.),
        'emergency_kwh': 0., 'surplus_kwh': 0., 'charge_kwh': 0., 'discharge_kwh': 0.,
        'min_soc_kwh': 6000., 'max_soc_kwh': 6000., 'runtime_seconds': 0., 'monthly_total_yuan': {}}


def accumulate(total, row):
    total['days'] += 1
    for k, v in row['costs'].items():
        total['costs'][k] += v
    for name, key in [('emergency_kwh','U'),('surplus_kwh','W'),('charge_kwh','C'),('discharge_kwh','D')]:
        total[name] += sum(row['schedule'][key])
    total['min_soc_kwh'] = min(total['min_soc_kwh'], min(row['schedule']['E']))
    total['max_soc_kwh'] = max(total['max_soc_kwh'], max(row['schedule']['E']))
    total['runtime_seconds'] += row['runtime_seconds']
    month = row['day'][:7]
    total['monthly_total_yuan'][month] = total['monthly_total_yuan'].get(month, 0.)+row['costs']['total_yuan']


def main():
    if (OUT/'result.json').exists():
        raise RuntimeError('Completed version exists; use a new explicit version')
    OUT.mkdir(parents=True, exist_ok=True)
    rows, source, digest = load_rows()
    days = parse_days(rows, delay_minutes=0)
    prices, price_hash = audited_csv('data/processed/team_delivery/day_base.csv')
    price = np.array([float(r['price']) for r in prices])
    base_report = json.loads((BASE/'result.json').read_text())
    base_check = json.loads((BASE/'independent_validation.json').read_text())
    if not base_check['passed'] or base_check['result_sha256'] != sha(BASE/'result.json'):
        raise ValueError('Baseline validation missing/stale')
    baseline = {}
    for mode in ('B0','B1'):
        if sha(BASE/f'{mode}.jsonl') != base_report['strategies'][mode]['daily_file_sha256']:
            raise ValueError('Baseline traces changed')
        baseline[mode] = [json.loads(line) for line in (BASE/f'{mode}.jsonl').open()]
    if base_report['january_selection']['chosen'] != METHODS:
        raise ValueError('Baseline methods differ')
    # Persist the candidate family before any evaluation actuals reach a solver.
    dump(OUT/'protocol.json', {'candidates': [asdict(c) for c in CANDIDATES],
        'training_dates': ['2025-01-15','2025-01-31'], 'residual_start': '2025-01-08',
        'methods': METHODS, 'controller_for_selection': 'B0', 'joint_B2_B3_parameters': True,
        'minimum_complexity_reference_percent': .25, 'baseline_result_sha256': sha(BASE/'result.json')})
    config = select_config(days[:31], price)
    freeze_hash = sha(OUT/'frozen_selection.json')
    names = ('B2','B3','fixedG_oracle','full_oracle')
    totals = {name: empty_summary() for name in names}
    states = {name: baseline[mode][30]['terminal_energy_kwh'] for name, mode in [('B2','B0'),('B3','B1')]}
    files = {name: (OUT/f'{name}.jsonl').open('w') for name in names}
    daily, started = [], time.monotonic()
    try:
        for i in range(31,365):
            before = time.monotonic()
            prediction, sources, audit = corrected(days, i, config)
            commitment = make_plan(prediction, price)
            shared_seconds = time.monotonic()-before
            for name, mode in [('B2','B0'),('B3','B1')]:
                before = time.monotonic()
                row = execute(days[i], price, prediction, sources, commitment, states[name], mode)
                states[name] = row['terminal_energy_kwh']
                row.update(strategy=name, margin=audit, frozen_selection_sha256=freeze_hash,
                           runtime_seconds=time.monotonic()-before+shared_seconds)
                files[name].write(json.dumps(row)+'\n')
                accumulate(totals[name], row)
                daily.append({'day': row['day'], 'strategy': name, **row['costs']})
            for name in ('fixedG_oracle','full_oracle'):
                before = time.monotonic()
                row = solve_oracle_day(actual_load=days[i].load_kwh, actual_pv=days[i].pv_kwh,
                    price=price, battery=BATTERY,
                    fixed_commitment=baseline['B0'][i]['planned_G'] if name == 'fixedG_oracle' else None)
                row.update(day=str(days[i].day), strategy=name, runtime_seconds=time.monotonic()-before)
                files[name].write(json.dumps(row)+'\n')
                accumulate(totals[name], row)
                daily.append({'day': row['day'], 'strategy': name, **row['costs']})
            if (i-30) % 60 == 0:
                print(i-30, '/334; elapsed', round(time.monotonic()-started,1), 's', flush=True)
    finally:
        for file in files.values():
            file.close()
    hashes = {str(source.relative_to(ROOT)): digest, 'data/processed/team_delivery/day_base.csv': price_hash}
    if any(sha(ROOT/p) != h for p,h in hashes.items()) or sha(OUT/'frozen_selection.json') != freeze_hash:
        raise ValueError('Inputs/frozen parameters changed')
    for name in names:
        totals[name]['daily_file_sha256'] = sha(OUT/f'{name}.jsonl')
    with (OUT/'daily_fees.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(daily[0])); w.writeheader(); w.writerows(daily)
    dump(OUT/'result.json', {'status': 'awaiting_independent_validation', 'strategies': totals,
        'input_sha256': hashes, 'frozen_selection_sha256': freeze_hash,
        'baseline_result_sha256': sha(BASE/'result.json'), 'policy': base_report['policy'],
        'evaluation_start': '2025-02-01', 'evaluation_end': '2025-12-31',
        'assumptions': base_report['assumptions'],
        'correction': 'add nonnegative scaled raw net-load residual quantile to forecast load; unchanged PV',
        'code_sha256': {str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__).resolve(),
            ROOT/'scripts/run_strict_q2.py', ROOT/'scripts/run_real_q23.py', ROOT/'scripts/run_real_q2_forecast.py',
            *sorted((ROOT/'src').rglob('*.py'))]}})
    print({k:v['costs'] for k,v in totals.items()}, flush=True)


if __name__ == '__main__':
    main()
