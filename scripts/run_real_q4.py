"""Q4 uses the unchanged Q2/Q3 engine under explicit known daily price curves."""
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from scripts.run_real_q23 import ROOT, audited_csv, dump, execute_day, forecast_actual_history, select_january
from scripts.run_real_q2_forecast import load_rows, parse_days
from src.q2.forecast import midnight
from src.q2.coordinator import PriceDay
from src.q3.pv import parse_forecasts
from scripts.verify_real_q23 import check_day

OUT = ROOT/'analysis/real_q4_candidate'
PRICE_POLICY = 'full_target_day_price_curve_known_at_midnight_candidate'


def parse_prices(rows, *, policy):
    if policy != PRICE_POLICY:
        raise ValueError('Explicit known-price candidate assumption required')
    if len(rows) != 365*144:
        raise ValueError('Expected complete annual price data')
    result = []
    for i in range(365):
        day = date(2025,1,1)+timedelta(days=i)
        block = rows[i*144:(i+1)*144]
        for slot, row in enumerate(block):
            end = midnight(day)+timedelta(minutes=10*(slot+1))
            label = end.strftime('%H:%M:%S') if slot < 143 else '0:00+1'
            if row['date'] != str(day) or int(row['slot']) != slot or row['time_str'] != label:
                raise ValueError('Price date/slot/endpoint mismatch; no sorting or filling')
        result.append(PriceDay(day, [float(r['price']) for r in block], midnight(day)))
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows, source, actual_hash = load_rows()
    days = parse_days(rows, delay_minutes=0)
    price_rows, price_hash = audited_csv('data/processed/team_delivery/dynamic_price.csv')
    prices = parse_prices(price_rows, policy=PRICE_POLICY)
    forecast_rows, pv_hash = audited_csv('data/processed/team_delivery/pv_forecast.csv')
    published = parse_forecasts(forecast_rows)
    selection = select_january(days)
    earlier_path = ROOT/'analysis/real_q23_candidate/result.json'
    earlier = json.loads(earlier_path.read_text())
    if selection != earlier['january_selection']:
        raise ValueError('Q4 must retain the frozen Q2/Q3 prediction methods')
    state, warmup_cost, worst = 6000., 0., 0.
    with (OUT/'january_warmup.jsonl').open('w') as f:
        for i in range(31):
            prediction, sources = ({'load':np.zeros(144),'pv':np.zeros(144)}, {}) if i == 0 else forecast_actual_history(days,i,{'load':'yesterday','pv':'yesterday'})
            row = execute_day(days[i], prices[i].price_yuan_per_kwh, state, prediction, sources, startup=i == 0)
            state, residual, costs = check_day(row, days[i], prices[i].price_yuan_per_kwh, state, True)
            warmup_cost += costs['total_yuan']; worst = max(worst,residual)
            f.write(json.dumps(row)+'\n')
    start_energy = state
    summaries = {}
    definitions = [('q4_2_main',False,(),True), ('q4_3_zero_only',True,(),True),
                   ('q4_3_stale_updates',True,(6,12,18),False), ('q4_3_main',True,(6,12,18),True)]
    for name, use_pv, updates, fresh in definitions:
        state = start_energy
        totals = dict.fromkeys(['planned_yuan','adjustment_yuan','emergency_yuan','total_yuan'],0.)
        emergency, residual_max, selected = 0., 0., {}
        with (OUT/f'{name}.jsonl').open('w') as f:
            for i in range(31,365):
                prediction, sources = forecast_actual_history(days,i,selection['chosen'])
                row = execute_day(days[i], prices[i].price_yuan_per_kwh, state, prediction, sources,
                    published=published if use_pv else None, update_hours=updates, fresh_updates=fresh)
                row['price_information'] = {'policy':PRICE_POLICY, 'available_at':prices[i].available_at.isoformat(),
                    'target_day':str(days[i].day),'availability_is_assumed':True,
                    'settlement_reference':'target physical slot price for initial, revision and emergency transactions'}
                state, residual, costs = check_day(row,days[i],prices[i].price_yuan_per_kwh,state,True)
                residual_max = max(residual_max,residual)
                for key in totals:totals[key] += costs[key]
                emergency += sum(row['schedule']['U'])
                if row['day'] in ['2025-03-20','2025-06-21','2025-09-23','2025-12-21']:selected[row['day']] = row
                f.write(json.dumps(row)+'\n')
                if (i-30)%100 == 0:print(name,i-30,'/334',flush=True)
        summaries[name] = {'days':334,'costs':totals,'emergency_kwh':emergency,
            'initial_energy_kwh':start_energy,'final_energy_kwh':state,'max_physical_residual_kwh':residual_max,
            'update_hours':updates,'fresh_pv_updates':fresh,'daily_file_sha256':hashlib.sha256((OUT/f'{name}.jsonl').read_bytes()).hexdigest()}
        if name in ('q4_2_main','q4_3_main'):dump(OUT/f'{name}_selected_days.json',selected)
        print(name,totals,flush=True)
    # Keep the old physical actions fixed, but settle at the new prices.
    # This separates a changed price environment from reoptimizing purchases.
    repricing = {}
    for n in (2,3):
        old_file = ROOT/f'analysis/real_q23_candidate/q{n}_main.jsonl'
        if hashlib.sha256(old_file.read_bytes()).hexdigest() != earlier['strategies'][f'q{n}_main']['daily_file_sha256']:
            raise ValueError('Q2/Q3 comparison source changed')
        total = 0.
        for i, line in enumerate(old_file.read_text().splitlines(),31):
            row = json.loads(line); p = prices[i].price_yuan_per_kwh
            value = float(p @ np.asarray(row['planned_G']) + 5*p @ np.asarray(row['schedule']['U']))
            for update in row['revisions']:
                delta = np.asarray(update['new_remaining_kwh'])-update['old_remaining_kwh']
                value += float(p[update['first_slot']:] @ (1.5*np.maximum(delta,0)-.5*np.maximum(-delta,0)))
            total += value
        repricing[str(n)] = {'fixed_tariff_original_cost_yuan':earlier['strategies'][f'q{n}_main']['costs']['total_yuan'],
            'old_actions_at_dynamic_prices_yuan':total,
            'dynamic_reoptimized_cost_yuan':summaries[f'q4_{n}_main']['costs']['total_yuan']}
    hashes = {str(source.relative_to(ROOT)):actual_hash,'data/processed/team_delivery/dynamic_price.csv':price_hash,
              'data/processed/team_delivery/pv_forecast.csv':pv_hash}
    if any(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h for p,h in hashes.items()):raise ValueError('Input changed')
    dump(OUT/'result.json',{'scope':'Q4 candidate conditional on known day prices; not causal price forecasting',
        'semantic_acceptance':False,'input_sha256':hashes,'source_unchanged':True,
        'evaluation_start':'2025-02-01','evaluation_end':'2025-12-31','evaluation_days':334,
        'price_policy':PRICE_POLICY,'price_range_yuan_per_kwh':[min(float(p.price_yuan_per_kwh.min()) for p in prices),max(float(p.price_yuan_per_kwh.max()) for p in prices)],
        'january_selection':selection,'assumptions':{**earlier['assumptions'],'price_information':PRICE_POLICY,
            'revision_price':'target-slot price, unchanged between contract updates; not decision-instant scalar price'},
        'warmup':{'start':'2025-01-01','end':'2025-01-31','days':31,'initial_energy_kwh':6000,
            'final_energy_kwh':start_energy,'cost_yuan':warmup_cost,'max_physical_residual_kwh':worst,
            'policy':'same startup/yesterday policy as Q2/Q3, rerun with daily dynamic prices',
            'daily_file_sha256':hashlib.sha256((OUT/'january_warmup.jsonl').read_bytes()).hexdigest()},
        'strategies':summaries,'repricing_controls':repricing,'q23_source_sha256':hashlib.sha256(earlier_path.read_bytes()).hexdigest(),
        'code_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [Path(__file__).resolve(),ROOT/'scripts/run_real_q23.py',ROOT/'scripts/run_real_q2_forecast.py',ROOT/'scripts/verify_real_q23.py',*sorted((ROOT/'src').rglob('*.py'))]}})


if __name__ == '__main__':main()
