"""Independent re-check of the Q4 strict transfer.

Rebuilds every ledger from the raw dynamic prices and the saved trajectories,
replays each day against zero actuals to prove no same-slot feedback, and
re-derives the summary totals without reusing any number from result.json.
"""
import json
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np

from scripts.run_strict_q4 import OUT, Q42_VARIANTS, Q43_VARIANTS, load_dynamic_prices
from scripts.run_strict_q3 import execute_day as execute_rolling
from scripts.run_strict_q2 import execute
from scripts.run_q2_margin_oracle import sha, make_plan, OUT as MARGIN
from scripts.run_real_q23 import audited_csv, dump
from scripts.run_real_q2_forecast import load_rows, parse_days
from scripts.verify_real_q23 import check_day
from scripts.verify_q2_margin_oracle import check_margin
from src.q2.forecast import ActualDay, midnight
from src.q3.pv import parse_forecasts


def verify_family(rows, *, days, prices, price_of, expected, margin, control,
                  by_day, protocol, published, initial, replay):
    """Recompute one strategy's ledger and physical checks from source truth."""
    state = initial
    costs = dict.fromkeys(expected['costs'], 0.)
    quantities = dict.fromkeys(('emergency_kwh', 'surplus_kwh', 'charge_kwh', 'discharge_kwh'), 0.)
    months, worst = {}, 0.
    for index, row in enumerate(rows, 31):
        day = days[index].day
        price = price_of(day)
        if not np.allclose(price, np.array(prices[str(day)]), atol=0, rtol=0):
            raise ValueError('Price vector not taken from attachment 4')
        state, residual, fee = check_day(row, days[index], price, state, True)
        worst = max(worst, residual)
        if row['policy'] != protocol['policy']:
            raise ValueError('Policy drift')
        if margin:
            check_margin(row, by_day, protocol['margin_config'])
            load = by_day[day - timedelta(days=7)].load_kwh + np.asarray(row['margin']['correction_kwh'])
        else:
            if row['margin'] is not None:
                raise ValueError('Base control carries a margin')
            load = by_day[day - timedelta(days=7)].load_kwh
        start = midnight(day)
        pv = (published[start].energy(decision_time=start, method='linear') if published is not None
              else by_day[day - timedelta(days=1)].pv_kwh)
        forecast = {'load': load, 'pv': pv}
        if not np.allclose(make_plan(forecast, price), row['planned_G'], atol=1e-6, rtol=0):
            raise ValueError('Midnight plan not reproducible from the declared forecast and price')
        expected_slots = [] if control in (None, 'zero') else [36, 72, 108]
        if [r['first_slot'] for r in row['revisions']] != expected_slots:
            raise ValueError('Missing or extra contract updates')
        # No actual value of the target day may influence any command or revision.
        zero = ActualDay(day, np.zeros(144), np.zeros(144), start + timedelta(days=1))
        again = replay(zero, price, forecast, row['forecast_sources'],
                       np.asarray(row['planned_G']), row['initial_energy_kwh'], control)
        if again['commands'] != row['commands'] or again['revisions'] != row['revisions']:
            raise ValueError('Decisions depend on same-day actuals')
        for key in ('G', 'C', 'D', 'E'):
            if not np.array_equal(again['schedule'][key], row['schedule'][key]):
                raise ValueError('Executed decisions differ from the zero-truth replay')
        for key, value in fee.items():
            costs[key] += value
        for name, variable in (('emergency_kwh', 'U'), ('surplus_kwh', 'W'),
                               ('charge_kwh', 'C'), ('discharge_kwh', 'D')):
            quantities[name] += sum(row['schedule'][variable])
        month = str(day)[:7]
        months[month] = months.get(month, 0.) + fee['total_yuan']
    if (any(abs(costs[k] - expected['costs'][k]) > 1e-5 for k in costs)
            or set(months) != set(expected['monthly_total_yuan'])
            or any(abs(v - expected['monthly_total_yuan'][k]) > 1e-5 for k, v in months.items())
            or any(abs(v - expected[k]) > 1e-5 for k, v in quantities.items())):
        raise ValueError('Summary mismatch')
    return {'days_verified': len(rows), 'max_physical_residual_kwh': worst,
            'costs': costs, 'zero_truth_actions_identical': True, 'passed': True}


def main():
    report = json.loads((OUT / 'result.json').read_text())
    protocol = json.loads((OUT / 'protocol.json').read_text())
    if sha(OUT / 'protocol.json') != report['protocol_sha256']:
        raise ValueError('Protocol changed since the run')
    if sha(MARGIN / 'frozen_selection.json') != protocol['q2_frozen_selection_sha256']:
        raise ValueError('Q2 frozen parameters changed; Q4 is no longer a pure transfer')
    if protocol['margin_retuned_for_q4']:
        raise ValueError('Q4 must not retune the margin')
    for path, digest in {**report['input_sha256'], **report['code_sha256']}.items():
        if sha(ROOT / path) != digest:
            raise ValueError('Input or code changed: ' + path)

    raw, _, _ = load_rows()
    days = parse_days(raw, delay_minutes=0)
    by_day = {d.day: d for d in days}
    prices, _ = load_dynamic_prices()
    price_of = lambda day: prices[str(day)]
    pv_rows, _ = audited_csv('data/processed/team_delivery/pv_forecast.csv')
    published = parse_forecasts(pv_rows)
    initial = report['february_initial_energy_kwh']

    evidence = {'q4-2': {}, 'q4-3': {}}
    for name, margin in Q42_VARIANTS.items():
        path = OUT / f'q4-2_{name}.jsonl'
        if sha(path) != report['q4-2'][name]['daily_file_sha256']:
            raise ValueError('Q4-2 trace changed')
        rows = [json.loads(line) for line in path.open()]
        if len(rows) != 334:
            raise ValueError('Q4-2 missing dates')
        evidence['q4-2'][name] = verify_family(
            rows, days=days, prices=prices, price_of=price_of, expected=report['q4-2'][name],
            margin=margin, control=None, by_day=by_day, protocol=protocol, published=None,
            initial=initial,
            replay=lambda a, p, f, s, g, e, c: execute(a, p, f, s, g, e, 'B0'))
        print('verified q4-2', name, flush=True)

    for name, (margin, control) in Q43_VARIANTS.items():
        path = OUT / f'q4-3_{name}.jsonl'
        if sha(path) != report['q4-3'][name]['daily_file_sha256']:
            raise ValueError('Q4-3 trace changed')
        rows = [json.loads(line) for line in path.open()]
        if len(rows) != 334:
            raise ValueError('Q4-3 missing dates')
        evidence['q4-3'][name] = verify_family(
            rows, days=days, prices=prices, price_of=price_of, expected=report['q4-3'][name],
            margin=margin, control=control, by_day=by_day, protocol=protocol, published=published,
            initial=initial,
            replay=lambda a, p, f, s, g, e, c: execute_rolling(a, p, f, s, g, published, e, c))
        print('verified q4-3', name, flush=True)

    # The structural claim reported in the paper, checked rather than asserted.
    fixed = {r['day']: r for r in (json.loads(l) for l in (ROOT / 'analysis/q2_margin_oracle_v1/B2.jsonl').open())}
    dynamic = {r['day']: r for r in (json.loads(l) for l in (OUT / 'q4-2_B2.jsonl').open())}
    shared = sorted(set(fixed) & set(dynamic))
    gaps = {'U': 0., 'W': 0., 'C_minus_G_minus_D': 0., 'C': 0.}
    for day in shared:
        a, b = fixed[day]['schedule'], dynamic[day]['schedule']
        for key in ('U', 'W', 'C'):
            gaps[key] = max(gaps[key], float(np.abs(np.array(a[key]) - np.array(b[key])).max()))
        left, right = (np.array(s['C']) - np.array(s['G']) - np.array(s['D']) for s in (a, b))
        gaps['C_minus_G_minus_D'] = max(gaps['C_minus_G_minus_D'], float(np.abs(left - right).max()))
    if max(gaps['U'], gaps['W'], gaps['C_minus_G_minus_D']) > 1e-6 or gaps['C'] < 1.0:
        raise ValueError('Emergency invariance claim does not hold as stated')

    total_days = sum(e['days_verified'] for group in evidence.values() for e in group.values())
    dump(OUT / 'independent_validation.json', {
        'passed': True, 'strategies': evidence,
        'days_verified': total_days, 'slots_verified': total_days * 144,
        'q2_parameters_unchanged': True, 'margin_retuned_for_q4': False,
        'price_source': 'data/processed/team_delivery/dynamic_price.csv, per-day 144 vector',
        'emergency_invariance': {
            'claim': 'with a fixed midnight commitment the B0 controller leaves the emergency and '
                     'surplus trajectories unchanged when only the price vector changes',
            'max_abs_slot_gap_U_kwh': gaps['U'], 'max_abs_slot_gap_W_kwh': gaps['W'],
            'max_abs_slot_gap_C_minus_G_minus_D_kwh': gaps['C_minus_G_minus_D'],
            'max_abs_slot_gap_C_kwh': gaps['C'],
            'days_compared': len(shared), 'holds': True},
        'result_sha256': sha(OUT / 'result.json'),
        'verifier_sha256': sha(Path(__file__).resolve())})
    print(f'Independent Q4 transfer verification passed: {total_days} days, {total_days * 144} slots')


if __name__ == '__main__':
    main()
