"""Independently replay saved contracts and physical equations against source truth."""
import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from scripts.run_real_q23 import ROOT, OUT, audited_csv, dump
from scripts.run_real_q2_forecast import load_rows, parse_days
from src.q2.forecast import midnight


def check_day(row, actual, price, initial, refund):
    if row['day'] != str(actual.day):
        raise ValueError('Date coverage mismatch')
    s = {k: np.asarray(v, dtype=float) for k, v in row['schedule'].items()}
    if set(s) != {'G', 'C', 'D', 'U', 'W', 'E'}:
        raise ValueError('Missing schedule variable')
    if any(v.shape != (145 if k == 'E' else 144,) or not np.isfinite(v).all() for k, v in s.items()):
        raise ValueError('Invalid schedule shape/value')
    residuals = [abs(s['E'][0]-initial), abs(s['E'][-1]-6000),
        abs(row['initial_energy_kwh']-s['E'][0]), abs(row['terminal_energy_kwh']-s['E'][-1]),
        np.max(np.abs(s['G']+actual.pv_kwh+s['D']+s['U']-actual.load_kwh-s['C']-s['W'])),
        np.max(np.abs(np.diff(s['E'])-.9*s['C']+s['D']/.9))]
    if max(residuals) > 1e-6 or any(np.min(v) < -1e-6 for v in s.values()):
        raise ValueError('Energy balance, state, boundary or nonnegativity failure')
    if (s['E'].min() < 1200-1e-6 or s['E'].max() > 10800+1e-6 or
            max(s['C'].max(), s['D'].max()) > 5000/6+1e-6 or
            np.any((s['C'] > 1e-6) & (s['D'] > 1e-6))):
        raise ValueError('Battery bounds or exclusivity failure')
    current = np.array(row['planned_G'], dtype=float)
    adjustment, previous_slot = 0., 0
    for revision in row['revisions']:
        slot = revision['first_slot']
        issue = datetime.fromisoformat(revision['issue_time'])
        if slot not in (36, 72, 108) or slot <= previous_slot or issue != midnight(actual.day)+timedelta(minutes=slot*10):
            raise ValueError('Invalid rolling chronology')
        previous_slot = slot
        if abs(revision['initial_energy_kwh']-s['E'][slot]) > 1e-6:
            raise ValueError('Rolling planner did not start from realized state')
        old, new = np.array(revision['old_remaining_kwh']), np.array(revision['new_remaining_kwh'])
        if not np.array_equal(old, current[slot:]):
            raise ValueError('Revision not relative to current commitment')
        delta = new-old
        value = float(price[slot:] @ (1.5*np.maximum(delta, 0)+(-.5 if refund else .5)*np.maximum(-delta, 0)))
        if abs(value-revision['incremental_cost_yuan']) > 1e-6:
            raise ValueError('Adjustment ledger discrepancy')
        current[slot:] = new
        adjustment += value
    if not np.array_equal(current, s['G']):
        raise ValueError('Final applicable commitments differ from executed purchases')
    costs = {'planned_yuan': float(price @ np.array(row['planned_G'])),
             'adjustment_yuan': adjustment, 'emergency_yuan': float(5*price @ s['U'])}
    costs['total_yuan'] = sum(costs.values())
    if any(abs(costs[k]-row['costs'][k]) > 1e-6 for k in costs):
        raise ValueError('Daily fee mismatch')
    for source in row['forecast_sources'].values():
        if date.fromisoformat(source['source_day']) >= actual.day or datetime.fromisoformat(source['available_at']) > midnight(actual.day):
            raise ValueError('Future history in forecast provenance')
    return float(s['E'][-1]), max(residuals), costs


def main():
    report = json.loads((OUT/'result.json').read_text())
    for path, digest in report['input_sha256'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest() != digest:
            raise ValueError('Input changed')
    rows, _, _ = load_rows()
    days = parse_days(rows, delay_minutes=0)
    prices, _ = audited_csv('data/processed/team_delivery/day_base.csv')
    price = np.array([float(r['price']) for r in prices])
    evidence = {}
    for name in ['january_warmup', *report['strategies']]:
        path = OUT/f'{name}.jsonl'
        if name != 'january_warmup' and hashlib.sha256(path.read_bytes()).hexdigest() != report['strategies'][name]['daily_file_sha256']:
            raise ValueError('Saved strategy file changed')
        records = [json.loads(line) for line in path.read_text().splitlines()]
        indices = range(31) if name == 'january_warmup' else range(31,365)
        if len(records) != len(indices):
            raise ValueError('Missing daily result')
        state, worst = 6000., 0.
        totals = dict.fromkeys(['planned_yuan', 'adjustment_yuan', 'emergency_yuan', 'total_yuan'], 0.)
        for row, i in zip(records, indices):
            state, residual, costs = check_day(row, days[i], price, state, name != 'q3_no_refund')
            worst = max(worst, residual)
            for key in totals:
                totals[key] += costs[key]
        expected = {'total_yuan': report['warmup']['cost_yuan']} if name == 'january_warmup' else report['strategies'][name]['costs']
        if any(abs(totals[k]-v) > 1e-5 for k, v in expected.items()):
            raise ValueError('Summary cost discrepancy')
        evidence[name] = {'days_verified': len(records), 'slots_verified': len(records)*144,
            'max_physical_residual_kwh': worst, 'costs': totals, 'passed': True}
    dump(OUT/'independent_validation.json', {'passed': True, 'strategies': evidence,
        'code_sha256': hashlib.sha256((ROOT/'scripts/verify_real_q23.py').read_bytes()).hexdigest(),
        'result_sha256': hashlib.sha256((OUT/'result.json').read_bytes()).hexdigest()})
    print('Independent replay passed:', sum(v['days_verified'] for v in evidence.values()), 'days')


if __name__ == '__main__':
    main()
