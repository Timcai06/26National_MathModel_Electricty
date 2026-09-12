"""Question 4 under the strict causal model: dynamic prices, everything else frozen.

Transfers the Q2 safety margin and the Q3 rolling contract ledger onto attachment 4
prices without refitting either. The controller, efficiencies, terminal policy and
settlement rules are the ones used for questions 2 and 3, so the only change is the
price input. Results are therefore comparable with the fixed-price experiments.
"""
import csv
import json
import sys
import time
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np

from scripts.run_real_q23 import audited_csv, dump, forecast_actual_history, BATTERY
from scripts.run_real_q2_forecast import load_rows, parse_days
from scripts.run_q2_margin_oracle import sha, make_plan, empty_summary, accumulate, corrected, OUT as MARGIN
from scripts.run_strict_q2 import execute
from scripts.run_strict_q3 import execute_day as execute_rolling
from src.q2.forecast import midnight
from src.q2.residual_margin import MarginConfig
from src.q2.strict_execution import POLICY
from src.q3.pv import parse_forecasts
from src.time_axis import time_semantics_attestation

OUT = ROOT / 'analysis/strict_q4_transfer_v1'
PRICE_POLICY = 'target-day dynamic price curve known at midnight; no price forecasting'
Q42_VARIANTS = {'B0': False, 'B2': True}                       # margin off / on, fixed commitment
Q43_VARIANTS = {f'{group}_{control}': (group == 'margin', control)
                for group in ('base', 'margin') for control in ('zero', 'stale', 'fresh')}


def load_dynamic_prices():
    """One 144-vector per calendar day, in the frozen interval-end slot order."""
    rows, digest = audited_csv('data/processed/team_delivery/dynamic_price.csv')
    by_day = defaultdict(dict)
    for row in rows:
        by_day[row['date']][int(row['slot'])] = float(row['price'])
    prices = {}
    for day, slots in by_day.items():
        if sorted(slots) != list(range(144)):
            raise ValueError(f'{day}: incomplete dynamic price day; no repair')
        prices[day] = np.array([slots[i] for i in range(144)])
    if len(prices) != 365:
        raise ValueError('Expected 365 dynamic price days')
    return prices, digest


def frozen_margin_config():
    """Reuse the January-frozen Q2 parameters; Q4 performs no retuning."""
    frozen = json.loads((MARGIN / 'frozen_selection.json').read_text())
    result = json.loads((MARGIN / 'result.json').read_text())
    check = json.loads((MARGIN / 'independent_validation.json').read_text())
    if (not check['passed'] or check['result_sha256'] != sha(MARGIN / 'result.json')
            or result['frozen_selection_sha256'] != sha(MARGIN / 'frozen_selection.json')):
        raise ValueError('Q2 frozen candidate lacks current validation')
    return MarginConfig(**frozen['selection']['config']), frozen['selection']['config']


def warmup(days, prices):
    """January under dynamic prices, so February starts from a comparable state."""
    state, rows = 6000., []
    for i in range(31):
        price = prices[str(days[i].day)]
        if i == 0:
            prediction, sources, commitment = {'load': np.zeros(144), 'pv': np.zeros(144)}, {}, np.zeros(144)
        else:
            prediction, sources = forecast_actual_history(days, i, {'load': 'yesterday', 'pv': 'yesterday'})
            commitment = make_plan(prediction, price)
        row = execute(days[i], price, prediction, sources, commitment, state, 'B0')
        row['runtime_seconds'] = 0.
        state = row['terminal_energy_kwh']
        rows.append(row)
    return state, rows


def run_q42(days, prices, config, initial):
    """Question 2 rebuilt on dynamic prices: fixed midnight commitment, no updates."""
    states = dict.fromkeys(Q42_VARIANTS, initial)
    totals = {name: empty_summary() for name in Q42_VARIANTS}
    files = {name: (OUT / f'q4-2_{name}.jsonl').open('w') for name in Q42_VARIANTS}
    daily, selected = [], {name: {} for name in Q42_VARIANTS}
    try:
        for i in range(31, 365):
            price = prices[str(days[i].day)]
            prediction, sources = forecast_actual_history(days, i, {'load': 'last_week', 'pv': 'yesterday'})
            enhanced, _, audit = corrected(days, i, config)
            plans = {False: make_plan(prediction, price), True: make_plan(enhanced, price)}
            for name, use_margin in Q42_VARIANTS.items():
                before = time.monotonic()
                row = execute(days[i], price, enhanced if use_margin else prediction, sources,
                              plans[use_margin], states[name], 'B0')
                row.update(strategy=name, margin=audit if use_margin else None,
                           runtime_seconds=time.monotonic() - before,
                           price_min=float(price.min()), price_max=float(price.max()))
                states[name] = row['terminal_energy_kwh']
                files[name].write(json.dumps(row) + '\n')
                accumulate(totals[name], row)
                daily.append({'day': row['day'], 'strategy': name, **row['costs']})
                if row['day'] in ('2025-03-20', '2025-06-21', '2025-09-23', '2025-12-21'):
                    selected[name][row['day']] = row
    finally:
        for handle in files.values():
            handle.close()
    return totals, daily, selected


def run_q43(days, prices, published, config, initial):
    """Question 3 rebuilt on dynamic prices: 6/12/18 updates and the same ledger."""
    states = dict.fromkeys(Q43_VARIANTS, initial)
    totals = {name: empty_summary() for name in Q43_VARIANTS}
    for entry in totals.values():
        entry.update(replan_attempts=0, material_revisions=0, increase_kwh=0., decrease_kwh=0.)
    files = {name: (OUT / f'q4-3_{name}.jsonl').open('w') for name in Q43_VARIANTS}
    daily, selected = [], {name: {} for name in Q43_VARIANTS}
    try:
        for i in range(31, 365):
            price = prices[str(days[i].day)]
            issue = midnight(days[i].day)
            prediction, sources = forecast_actual_history(days, i, {'load': 'last_week', 'pv': 'yesterday'})
            enhanced, _, audit = corrected(days, i, config)
            zero_pv = published[issue].energy(decision_time=issue, method='linear')
            plans = {group: make_plan({'load': p['load'], 'pv': zero_pv}, price)
                     for group, p in (('base', prediction), ('margin', enhanced))}
            for name, (use_margin, control) in Q43_VARIANTS.items():
                before = time.monotonic()
                row = execute_rolling(days[i], price, enhanced if use_margin else prediction, sources,
                                      plans['margin' if use_margin else 'base'], published,
                                      states[name], control)
                row.update(strategy=name, margin=audit if use_margin else None,
                           runtime_seconds=time.monotonic() - before,
                           price_min=float(price.min()), price_max=float(price.max()))
                states[name] = row['terminal_energy_kwh']
                files[name].write(json.dumps(row) + '\n')
                accumulate(totals[name], row)
                for revision in row['revisions']:
                    totals[name]['replan_attempts'] += 1
                    totals[name]['material_revisions'] += int(
                        max(revision['increase_kwh'], revision['decrease_kwh']) > 1e-5)
                    for key in ('increase_kwh', 'decrease_kwh'):
                        totals[name][key] += revision[key]
                daily.append({'day': row['day'], 'strategy': name, **row['costs']})
                if row['day'] in ('2025-03-20', '2025-06-21', '2025-09-23', '2025-12-21'):
                    selected[name][row['day']] = row
    finally:
        for handle in files.values():
            handle.close()
    return totals, daily, selected


def price_blind_control(days, prices, fixed_price, config, initial):
    """Plan on the fixed representative-day tariff, settle on the real dynamic price.

    Isolates how much of the Q4 result comes from actually using the dynamic price
    in planning, rather than from the prices themselves being different.
    """
    state, total = initial, empty_summary()
    with (OUT / 'q4-2_B2_price_blind.jsonl').open('w') as handle:
        for i in range(31, 365):
            price = prices[str(days[i].day)]
            enhanced, sources, audit = corrected(days, i, config)
            commitment = make_plan(enhanced, fixed_price)   # planned without the dynamic curve
            before = time.monotonic()
            row = execute(days[i], price, enhanced, sources, commitment, state, 'B0')
            row.update(strategy='B2_price_blind', margin=audit, runtime_seconds=time.monotonic() - before)
            state = row['terminal_energy_kwh']
            handle.write(json.dumps(row) + '\n')
            accumulate(total, row)
    return total


def main():
    if (OUT / 'result.json').exists():
        raise RuntimeError('Completed version exists; use a new version directory')
    OUT.mkdir(parents=True, exist_ok=True)
    raw, source, digest = load_rows()
    days = parse_days(raw, delay_minutes=0)
    prices, price_hash = load_dynamic_prices()
    fixed_rows, fixed_hash = audited_csv('data/processed/team_delivery/day_base.csv')
    fixed_price = np.array([float(r['price']) for r in fixed_rows])
    pv_rows, pv_hash = audited_csv('data/processed/team_delivery/pv_forecast.csv')
    published = parse_forecasts(pv_rows)
    config, config_dict = frozen_margin_config()

    protocol = {
        'policy': POLICY, 'price_policy': PRICE_POLICY,
        'scope': 'Q4 strict transfer: dynamic prices only; controller, margin and ledger unchanged',
        'margin_config': config_dict, 'margin_retuned_for_q4': False,
        'q2_frozen_selection_sha256': sha(MARGIN / 'frozen_selection.json'),
        'warmup': 'January 1-31 replayed under dynamic prices with the B0 controller',
        'q4-2_variants': list(Q42_VARIANTS), 'q4-3_variants': list(Q43_VARIANTS),
        'updates': [6, 12, 18], 'refund': 'refund cancelled cost plus 50% penalty, relative to current commitment',
        'terminal': 'daily6000', 'efficiency': '.9 each', 'power_side': 'bus', 'conversion': 'linear',
        'time_semantics': time_semantics_attestation(),
    }
    dump(OUT / 'protocol.json', protocol)
    protocol_hash = sha(OUT / 'protocol.json')

    started = time.monotonic()
    initial, warmup_rows = warmup(days, prices)
    with (OUT / 'warmup.jsonl').open('w') as handle:
        for row in warmup_rows:
            handle.write(json.dumps(row) + '\n')
    print(f'warmup done, Feb 1 initial energy {initial:.3f} kWh', flush=True)

    q42_totals, q42_daily, q42_selected = run_q42(days, prices, config, initial)
    print('Q4-2 done', {k: round(v['costs']['total_yuan'], 2) for k, v in q42_totals.items()}, flush=True)
    q43_totals, q43_daily, q43_selected = run_q43(days, prices, published, config, initial)
    print('Q4-3 done', {k: round(v['costs']['total_yuan'], 2) for k, v in q43_totals.items()}, flush=True)
    blind = price_blind_control(days, prices, fixed_price, config, initial)
    print('price-blind control done', round(blind['costs']['total_yuan'], 2), flush=True)

    hashes = {str(source.relative_to(ROOT)): digest,
              'data/processed/team_delivery/dynamic_price.csv': price_hash,
              'data/processed/team_delivery/day_base.csv': fixed_hash,
              'data/processed/team_delivery/pv_forecast.csv': pv_hash}
    if any(sha(ROOT / p) != h for p, h in hashes.items()) or sha(OUT / 'protocol.json') != protocol_hash:
        raise ValueError('Input/protocol changed during the run')
    for name, entry in list(q42_totals.items()):
        entry['daily_file_sha256'] = sha(OUT / f'q4-2_{name}.jsonl')
    for name, entry in list(q43_totals.items()):
        entry['daily_file_sha256'] = sha(OUT / f'q4-3_{name}.jsonl')
    blind['daily_file_sha256'] = sha(OUT / 'q4-2_B2_price_blind.jsonl')

    with (OUT / 'daily_fees.csv').open('w', newline='') as handle:
        rows = [{'question': 'q4-2', **r} for r in q42_daily] + [{'question': 'q4-3', **r} for r in q43_daily]
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    dump(OUT / 'selected_days.json', {'q4-2': q42_selected, 'q4-3': q43_selected})
    dump(OUT / 'result.json', {
        'status': 'awaiting_independent_validation', 'policy': POLICY, 'price_policy': PRICE_POLICY,
        'protocol_sha256': protocol_hash, 'input_sha256': hashes,
        'evaluation_start': '2025-02-01', 'evaluation_end': '2025-12-31', 'days': 334,
        'february_initial_energy_kwh': initial,
        'q4-2': q42_totals, 'q4-3': q43_totals, 'price_blind_control': blind,
        'total_runtime_seconds': time.monotonic() - started,
        'code_sha256': {str(p.relative_to(ROOT)): sha(p) for p in [
            Path(__file__).resolve(), ROOT / 'scripts/run_strict_q2.py', ROOT / 'scripts/run_strict_q3.py',
            ROOT / 'scripts/run_q2_margin_oracle.py', ROOT / 'scripts/run_real_q23.py',
            ROOT / 'scripts/run_real_q2_forecast.py', *sorted((ROOT / 'src').rglob('*.py'))]}})
    print(json.dumps({'q4-2': {k: v['costs'] for k, v in q42_totals.items()},
                      'q4-3': {k: v['costs'] for k, v in q43_totals.items()},
                      'price_blind': blind['costs']}, indent=2), flush=True)


if __name__ == '__main__':
    main()
