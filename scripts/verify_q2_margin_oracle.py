"""Recompute January selection, as-of margins, actions, bounds and ledgers."""
from pathlib import Path
from datetime import date, datetime, timedelta
from dataclasses import asdict
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from scripts.run_q2_margin_oracle import OUT, BASE, sha
from scripts.run_real_q23 import audited_csv, dump, BATTERY
from scripts.run_real_q2_forecast import load_rows, parse_days
from scripts.verify_real_q23 import check_day
from src.q2.residual_margin import CANDIDATES
from src.q2.strict_execution import StrictExecutor
from src.q2.forecast import midnight


def check_margin(row, by_day, expected_config):
    audit=row['margin']; config=audit['config']
    if config != expected_config:
        raise ValueError('Margin parameters not frozen')
    target=date.fromisoformat(row['day']); start=midnight(target)
    if audit['available_at'] != start.isoformat():
        raise ValueError('Forecast issue time mismatch')
    expected_dates=[target-timedelta(days=n) for n in range(config['window_days'],0,-1)]
    residuals=[]; provenance=[]
    for day in expected_dates:
        a=by_day.get(day); l=by_day.get(day-timedelta(days=7)); p=by_day.get(day-timedelta(days=1))
        if a is None or l is None or p is None:
            continue
        if a.available_at>start or l.available_at>midnight(day) or p.available_at>midnight(day):
            continue
        residuals.append(a.load_kwh-a.pv_kwh-l.load_kwh+p.pv_kwh)
        provenance.append({'day':str(day),'available_at':a.available_at.isoformat(),
                           'load_source_day':str(l.day),'pv_source_day':str(p.day)})
    if audit['residual_days'] != provenance:
        raise ValueError('As-of residual library mismatch')
    correction=np.zeros(144); qs=[]
    if len(residuals)>=config['min_days']:
        errors=np.asarray(residuals)
        for j in range(0,144,config['bucket_slots']):
            q=float(np.quantile(errors[:,j:j+config['bucket_slots']],config['tau'],method='linear'))
            qs.append(q)
            correction[j:j+config['bucket_slots']]=config['scale']*max(0.,q)
    if not np.allclose(correction,audit['correction_kwh'],atol=1e-10,rtol=0) or not np.allclose(qs,audit['bucket_raw_quantiles_kwh'],atol=1e-10,rtol=0):
        raise ValueError('Residual formula mismatch')
    for field,lag in [('load',7),('pv',1)]:
        s=row['forecast_sources'][field]; source=by_day[target-timedelta(days=lag)]
        if s != {'source_day':str(source.day),'available_at':source.available_at.isoformat()}:
            raise ValueError('Baseline source mismatch')
    load=by_day[target-timedelta(days=7)].load_kwh+correction
    pv=by_day[target-timedelta(days=1)].pv_kwh
    return load,pv


def replay_commands(row, price, forecast):
    start=midnight(date.fromisoformat(row['day']))
    c=StrictExecutor(day=date.fromisoformat(row['day']),commitment=row['planned_G'],price=price,
        forecast_load=forecast[0],forecast_pv=forecast[1],forecast_available_at=start,
        battery=BATTERY,initial_energy=row['initial_energy_kwh'],mode=row['controller'])
    if len(row['commands'])!=144:
        raise ValueError('Missing commands')
    # Deliberately settle a synthetic all-zero actual day. A causal fixed-action
    # controller with frozen forecast must generate the same C/D for every slot.
    for i, command in enumerate(row['commands']):
        regenerated=c.decide(start+timedelta(minutes=10*i))
        expected=asdict(regenerated)
        if any(expected[k]!=command[k] for k in expected if k not in ('C','D')):
            raise ValueError('Command provenance mismatch')
        if max(abs(expected[k]-command[k]) for k in ('C','D'))>1e-6:
            raise ValueError('Commands depend on actuals or wrong forecast')
        if command['C']!=row['schedule']['C'][i] or command['D']!=row['schedule']['D'][i]:
            raise ValueError('Executed action differs from command')
        c.settle(load_kwh=0.,pv_kwh=0.,available_at=start+timedelta(minutes=10*(i+1)))
    if [x['slot'] for x in row['solves']] != (list(range(0,144,6)) if row['controller']=='B1' else []):
        raise ValueError('Wrong replan frequency')


def main():
    report=json.loads((OUT/'result.json').read_text())
    for p,h in {**report['input_sha256'],**report['code_sha256']}.items():
        if sha(ROOT/p)!=h:
            raise ValueError('Source/code mismatch: '+p)
    if sha(OUT/'frozen_selection.json')!=report['frozen_selection_sha256'] or sha(BASE/'result.json')!=report['baseline_result_sha256']:
        raise ValueError('Frozen selection/baseline changed')
    frozen=json.loads((OUT/'frozen_selection.json').read_text())
    if sha(OUT/'january_development.jsonl')!=frozen['development_sha256']:
        raise ValueError('Development traces changed')
    raw,_,_=load_rows(); days=parse_days(raw,delay_minutes=0)
    by_day={d.day:d for d in days}
    prices,_=audited_csv('data/processed/team_delivery/day_base.csv')
    price=np.array([float(r['price']) for r in prices])
    scores={i:0. for i in range(len(CANDIDATES))}; seen=set()
    state={i:6000. for i in scores}
    for line in (OUT/'january_development.jsonl').open():
        row=json.loads(line); cid=row['candidate_id']; day=date.fromisoformat(row['day'])
        if cid not in scores or not date(2025,1,15)<=day<=date(2025,1,31) or (cid,day) in seen:
            raise ValueError('Development coverage mismatch')
        seen.add((cid,day))
        forecast=check_margin(row,by_day,asdict(CANDIDATES[cid]))
        state[cid],_,cost=check_day(row,by_day[day],price,state[cid],True)
        replay_commands(row,price,forecast)
        scores[cid]+=cost['total_yuan']
    if len(seen)!=9*17:
        raise ValueError('Missing January experiments')
    for score in frozen['scores']:
        if abs(scores[score['candidate_id']]-score['january_total_yuan'])>1e-5:
            raise ValueError('January score mismatch')
    chosen=min(scores,key=lambda i:(scores[i],i))
    if chosen!=frozen['selection']['candidate_id'] or frozen['selection']['config']!=asdict(CANDIDATES[chosen]):
        raise ValueError('Selection not January optimum within frozen grid')
    base={m:[json.loads(l) for l in (BASE/f'{m}.jsonl').open()] for m in ('B0','B1')}
    base_report=json.loads((BASE/'result.json').read_text())
    for m in base:
        if sha(BASE/f'{m}.jsonl')!=base_report['strategies'][m]['daily_file_sha256']:
            raise ValueError('Baseline trace mismatch')
    traces={}; evidence={}
    for name,expected in report['strategies'].items():
        path=OUT/f'{name}.jsonl'
        if sha(path)!=expected['daily_file_sha256']:
            raise ValueError('Saved trace changed')
        rows=[json.loads(l) for l in path.open()]
        if len(rows)!=334:
            raise ValueError('Evaluation date coverage mismatch')
        traces[name]=rows; state=6000.; worst=0.
        costs=dict.fromkeys(expected['costs'],0.); monthly={}
        quantities=dict.fromkeys(('emergency_kwh','surplus_kwh','charge_kwh','discharge_kwh'),0.)
        for i,row in enumerate(rows,31):
            state,residual,fee=check_day(row,days[i],price,state,True)
            worst=max(worst,residual)
            if name in ('B2','B3'):
                if row['controller']!=('B0' if name=='B2' else 'B1') or row['policy']!=report['policy'] or row['frozen_selection_sha256']!=report['frozen_selection_sha256']:
                    raise ValueError('Policy/parameters differ')
                forecast=check_margin(row,by_day,frozen['selection']['config'])
                replay_commands(row,price,forecast)
            elif row['policy']!='perfect_information_diagnostic_not_causal':
                raise ValueError('Oracle must be marked noncausal')
            if name=='fixedG_oracle' and not np.array_equal(row['planned_G'],base['B0'][i]['planned_G']):
                raise ValueError('Fixed-G oracle changed commitment')
            for k,v in fee.items():costs[k]+=v
            for metric,key in [('emergency_kwh','U'),('surplus_kwh','W'),('charge_kwh','C'),('discharge_kwh','D')]:
                quantities[metric]+=sum(row['schedule'][key])
            month=row['day'][:7]; monthly[month]=monthly.get(month,0.)+fee['total_yuan']
        if any(abs(costs[k]-expected['costs'][k])>1e-5 for k in costs) or monthly!=expected['monthly_total_yuan'] or any(abs(v-expected[k])>1e-5 for k,v in quantities.items()):
            raise ValueError('Summary mismatch')
        evidence[name]={'days_verified':334,'max_physical_residual_kwh':worst,'costs':costs,'passed':True}
        print('Verified',name,flush=True)
    for j in range(334):
        b2,b3,fixed,full=[traces[n][j] for n in ('B2','B3','fixedG_oracle','full_oracle')]
        if not np.array_equal(b2['planned_G'],b3['planned_G']):
            raise ValueError('B2/B3 contracts differ')
        f=fixed['costs']['total_yuan']; o=full['costs']['total_yuan']
        if f>min(base[m][j+31]['costs']['total_yuan'] for m in base)+1e-5 or o>f+1e-5 or o>min(b2['costs']['total_yuan'],b3['costs']['total_yuan'])+1e-5:
            raise ValueError('Perfect-information bound violated')
    dump(OUT/'independent_validation.json', {'passed':True,'january_days_verified':len(seen),
        'evaluation_day_traces_verified':4*334,'strategies':evidence,
        'paired_B2_B3_G_equal':True,'all_daily_oracle_bounds_passed':True,
        'all_causal_actions_replayed_with_zero_actuals':True,'january_selection_recomputed':True,
        'result_sha256':sha(OUT/'result.json'),'verifier_sha256':sha(Path(__file__).resolve())})
    print('Independent checks passed:153 January +1336 evaluation day traces')


if __name__=='__main__':main()
