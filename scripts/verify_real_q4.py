"""Reopen Q4 schedules and independently reconcile dynamic-price cash flows."""
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from scripts.run_real_q4 import ROOT, OUT, PRICE_POLICY, parse_prices
from scripts.run_real_q23 import audited_csv, dump
from scripts.run_real_q2_forecast import load_rows, parse_days
from scripts.verify_real_q23 import check_day
from src.q2.forecast import midnight


def main():
    report = json.loads((OUT/'result.json').read_text())
    for path, digest in report['input_sha256'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest() != digest:raise ValueError('Input changed')
    rows, _, _ = load_rows()
    days = parse_days(rows,delay_minutes=0)
    prices = parse_prices(audited_csv('data/processed/team_delivery/dynamic_price.csv')[0],policy=PRICE_POLICY)
    evidence = {}
    for name in ['january_warmup', *report['strategies']]:
        path = OUT/f'{name}.jsonl'
        expected = report['warmup'] if name == 'january_warmup' else report['strategies'][name]
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected['daily_file_sha256']:raise ValueError('Schedule changed')
        records = [json.loads(line) for line in path.read_text().splitlines()]
        indices = range(31) if name == 'january_warmup' else range(31,365)
        if len(records) != len(indices):raise ValueError('Date coverage mismatch')
        state, worst = 6000., 0.
        totals = dict.fromkeys(['planned_yuan','adjustment_yuan','emergency_yuan','total_yuan'],0.)
        for row, i in zip(records,indices):
            if name != 'january_warmup':
                info = row['price_information']
                if info['policy'] != PRICE_POLICY or info['available_at'] != midnight(days[i].day).isoformat() or not info['availability_is_assumed']:
                    raise ValueError('Price availability provenance missing')
            state,residual,costs = check_day(row,days[i],prices[i].price_yuan_per_kwh,state,True)
            worst = max(worst,residual)
            for key in totals:totals[key] += costs[key]
        expected_costs = {'total_yuan':expected['cost_yuan']} if name == 'january_warmup' else expected['costs']
        if any(abs(totals[k]-v) > 1e-5 for k,v in expected_costs.items()):raise ValueError('Aggregated fee mismatch')
        evidence[name] = {'passed':True,'days_verified':len(records),'slots_verified':len(records)*144,
            'max_physical_residual_kwh':worst,'costs':totals}
    control_checks = {}
    earlier = ROOT/'analysis/real_q23_candidate/result.json'
    if hashlib.sha256(earlier.read_bytes()).hexdigest() != report['q23_source_sha256']:raise ValueError('Original comparison manifest changed')
    for number in (2,3):
        rows = [json.loads(line) for line in (earlier.parent/f'q{number}_main.jsonl').read_text().splitlines()]
        total = 0.
        for i,row in enumerate(rows,31):
            price = prices[i].price_yuan_per_kwh
            total += float(price @ np.array(row['schedule']['G']) + 5*price @ np.array(row['schedule']['U']))
            for update in row['revisions']:
                total += float(.5*price[update['first_slot']:] @ np.abs(np.array(update['new_remaining_kwh'])-update['old_remaining_kwh']))
        residual = abs(total-report['repricing_controls'][str(number)]['old_actions_at_dynamic_prices_yuan'])
        if residual > 1e-5:raise ValueError('Fixed-action repricing failed')
        control_checks[str(number)] = residual
    dump(OUT/'independent_validation.json',{'passed':True,'strategies':evidence,'repricing_residuals_yuan':control_checks,
        'result_sha256':hashlib.sha256((OUT/'result.json').read_bytes()).hexdigest(),
        'validator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    print('Independent Q4 replay passed:',sum(v['days_verified'] for v in evidence.values()),'day trajectories')


if __name__ == '__main__':main()
