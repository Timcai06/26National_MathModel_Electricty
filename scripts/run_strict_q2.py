"""B0/B1 fixed-commitment comparison; never overwrite legacy outputs."""
import csv
import hashlib
import json
from datetime import timedelta
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from scripts.run_real_q23 import audited_csv, dump, select_january, forecast_actual_history, BATTERY
from scripts.run_real_q2_forecast import load_rows, parse_days
from src.core.model import build_microgrid_constraints
from src.core.solver import solve_model
from src.q2.forecast import midnight
from src.q2.strict_execution import StrictExecutor, POLICY

OUT = ROOT/'analysis/strict_q2_round2_v1'


def execute(actual, price, prediction, sources, commitment, initial, mode):
    start = midnight(actual.day)
    executor = StrictExecutor(day=actual.day, commitment=commitment, price=price,
        forecast_load=prediction['load'], forecast_pv=prediction['pv'], forecast_available_at=start,
        battery=BATTERY, initial_energy=initial, mode=mode)
    for i in range(144):
        executor.decide(start+timedelta(minutes=10*i))
        executor.settle(load_kwh=float(actual.load_kwh[i]), pv_kwh=float(actual.pv_kwh[i]),
                        available_at=start+timedelta(minutes=10*(i+1)))
    row = executor.finish()
    row.update(day=str(actual.day), initial_energy_kwh=initial, terminal_energy_kwh=executor.energy,
               forecast_sources=sources, planned_G=commitment.tolist(), revisions=[])
    return row


def main():
    if (OUT/'result.json').exists():
        raise RuntimeError('Completed version exists; choose a new output version')
    OUT.mkdir(parents=True, exist_ok=True)
    rows, source, digest = load_rows()
    days = parse_days(rows, delay_minutes=0)
    prices, price_hash = audited_csv('data/processed/team_delivery/day_base.csv')
    price = np.array([float(r['price']) for r in prices])
    selection = select_january(days)
    hashes = {str(source.relative_to(ROOT)): digest,
              'data/processed/team_delivery/day_base.csv': price_hash}
    summary = {mode: {'costs': dict.fromkeys(('planned_yuan', 'adjustment_yuan', 'emergency_yuan', 'total_yuan'), 0.),
        'warmup_cost_yuan': 0., 'runtime_seconds': 0., 'monthly_total_yuan': {},
        'emergency_kwh': 0., 'surplus_kwh': 0., 'charge_kwh': 0., 'discharge_kwh': 0.,
        'min_soc_kwh': 6000., 'max_soc_kwh': 6000.,
        'last_slots_emergency_kwh': {str(n): 0. for n in (6, 12, 24)}} for mode in ('B0', 'B1')}
    states = dict.fromkeys(summary, 6000.)
    files = {mode: (OUT/f'{mode}.jsonl').open('w') for mode in summary}
    started = time.monotonic()
    daily_fees = []
    try:
        for i, actual in enumerate(days):
            if i == 0:
                prediction, sources = {'load': np.zeros(144), 'pv': np.zeros(144)}, {}
                commitment = np.zeros(144)
            else:
                chosen = {'load': 'yesterday', 'pv': 'yesterday'} if i < 31 else selection['chosen']
                prediction, sources = forecast_actual_history(days, i, chosen)
                model = build_microgrid_constraints(load_kwh=prediction['load'], pv_kwh=prediction['pv'],
                    battery_params=BATTERY, initial_energy_kwh=6000., terminal_energy_kwh=6000.)
                plan = solve_model(model, price_yuan_per_kwh=price)
                if plan.status != 'optimal':
                    raise RuntimeError('Day-ahead failure: '+plan.status)
                commitment = plan.schedule['G']
            for mode in summary:
                before = time.monotonic()
                row = execute(actual, price, prediction, sources, commitment, states[mode], mode)
                elapsed = time.monotonic()-before
                row['runtime_seconds'] = elapsed
                row['period'] = 'warmup' if i < 31 else 'evaluation'
                files[mode].write(json.dumps(row)+'\n')
                states[mode] = row['terminal_energy_kwh']
                totals = summary[mode]
                if i < 31:
                    totals['warmup_cost_yuan'] += row['costs']['total_yuan']
                    continue
                totals['runtime_seconds'] += elapsed
                for key, value in row['costs'].items():
                    totals['costs'][key] += value
                s = row['schedule']
                for metric, key in [('emergency_kwh', 'U'), ('surplus_kwh', 'W'), ('charge_kwh', 'C'), ('discharge_kwh', 'D')]:
                    totals[metric] += sum(s[key])
                totals['min_soc_kwh'] = min(totals['min_soc_kwh'], min(s['E']))
                totals['max_soc_kwh'] = max(totals['max_soc_kwh'], max(s['E']))
                for n in (6, 12, 24):
                    totals['last_slots_emergency_kwh'][str(n)] += sum(s['U'][-n:])
                month = str(actual.day)[:7]
                totals['monthly_total_yuan'][month] = totals['monthly_total_yuan'].get(month, 0.)+row['costs']['total_yuan']
                daily_fees.append({'day': str(actual.day), 'strategy': mode, **row['costs']})
            if (i+1) % 30 == 0:
                print(f'{i+1}/365 days; elapsed {time.monotonic()-started:.1f}s', flush=True)
    finally:
        for f in files.values():
            f.close()
    for mode, totals in summary.items():
        totals['daily_file_sha256'] = hashlib.sha256((OUT/f'{mode}.jsonl').read_bytes()).hexdigest()
        totals['evaluation_days'] = 334
    if any(hashlib.sha256((ROOT/p).read_bytes()).hexdigest() != h for p, h in hashes.items()):
        raise RuntimeError('Input changed')
    with (OUT/'daily_fees.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(daily_fees[0]))
        writer.writeheader()
        writer.writerows(daily_fees)
    dump(OUT/'result.json', {'policy': POLICY, 'status': 'awaiting_independent_validation',
        'input_sha256': hashes, 'january_selection': selection, 'strategies': summary,
        'total_runtime_seconds': time.monotonic()-started,
        'assumptions': {'terminal': 'daily6000', 'efficiency': '.9 each', 'power_side': 'bus',
            'forecast': 'frozen midnight; no intraday residual correction', 'grid': 'unlimited slot-end residual settlement at 5p',
            'comparison': 'identical daily G; only battery policy differs; no promise of MPC improvement'},
        'code_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__).resolve(), ROOT/'scripts/run_real_q23.py', ROOT/'scripts/run_real_q2_forecast.py', *sorted((ROOT/'src').rglob('*.py'))]}})
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
