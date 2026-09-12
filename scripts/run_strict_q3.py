"""Six predeclared Q3 comparisons under the strict slot-start convention."""
from pathlib import Path
from datetime import timedelta
import csv
import json
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from scripts.run_real_q23 import audited_csv,dump,forecast_actual_history,BATTERY
from scripts.run_real_q2_forecast import load_rows,parse_days
from scripts.run_q2_margin_oracle import sha,make_plan,empty_summary,accumulate,corrected,OUT as MARGIN
from scripts.run_strict_q2 import OUT as BASE
from src.q2.forecast import midnight
from src.q2.residual_margin import MarginConfig
from src.q3.pv import parse_forecasts
from src.q3.planning import replan,adjustment_cost
from src.q3.strict_execution import StrictRollingExecutor
from src.q2.strict_execution import POLICY

OUT=ROOT/'analysis/strict_q3_transfer_v1'
VARIANTS={f'{group}_{control}':(group=='margin',control) for group in ('base','margin')
          for control in ('zero','stale','fresh')}


def execute_day(actual,price,prediction,sources,commitment,published,initial,control):
    if control not in ('zero','stale','fresh'):
        raise ValueError('Unknown Q3 control')
    issue=midnight(actual.day)
    midnight_pv=published[issue].energy(decision_time=issue,method='linear')
    executor=StrictRollingExecutor(day=actual.day,commitment=commitment,price=price,
        forecast_load=prediction['load'],forecast_pv=midnight_pv,forecast_available_at=issue,
        battery=BATTERY,initial_energy=initial)
    revisions=[]
    for slot in range(144):
        decision=issue+timedelta(minutes=10*slot)
        if slot in (36,72,108) and control!='zero':
            forecast_issue=decision if control=='fresh' else issue
            remaining_pv=(published[forecast_issue].energy(decision_time=decision,method='linear')[:144-slot]
                          if control=='fresh' else midnight_pv[slot:])
            old=executor.g[slot:].copy()
            update=replan(load_kwh=prediction['load'][slot:],pv_kwh=remaining_pv,
                old_commitment=old,price=price[slot:],initial_energy=executor.energy,battery=BATTERY,refund=True)
            new=executor.g.copy();new[slot:]=update['G']
            delta=executor.revise(commitment=new,remaining_load=prediction['load'][slot:],
                remaining_pv=remaining_pv,decision_time=decision,forecast_available_at=forecast_issue)
            revisions.append({'issue_time':decision.isoformat(),'first_slot':slot,
                'forecast_issue_time':forecast_issue.isoformat(),'initial_energy_kwh':executor.energy,
                'old_remaining_kwh':old.tolist(),'new_remaining_kwh':new[slot:].tolist(),
                'incremental_cost_yuan':adjustment_cost(old,new[slot:],price[slot:],refund=True),
                **delta,'diagnostics':update['diagnostics'],'objective_residual_yuan':update['objective_residual_yuan']})
        executor.decide(decision)
        executor.settle(load_kwh=float(actual.load_kwh[slot]),pv_kwh=float(actual.pv_kwh[slot]),
                        available_at=decision+timedelta(minutes=10))
    row=executor.finish()
    base=float(price@commitment)
    adjustment=sum(r['incremental_cost_yuan'] for r in revisions)
    penalty=sum(float(.5*price[r['first_slot']:]@np.abs(np.asarray(r['new_remaining_kwh'])-r['old_remaining_kwh'])) for r in revisions)
    ledger_residual=abs(base+adjustment-float(price@executor.g)-penalty)
    if ledger_residual>1e-6:
        raise ValueError('Q3 contract ledger mismatch')
    row['costs'].update(planned_yuan=base,adjustment_yuan=adjustment,
                        total_yuan=base+adjustment+row['costs']['emergency_yuan'])
    row.update(day=str(actual.day),initial_energy_kwh=initial,terminal_energy_kwh=executor.energy,
        forecast_sources=sources,planned_G=commitment.tolist(),revisions=revisions,
        pv_issue_time=issue.isoformat(),control=control,ledger_residual_yuan=ledger_residual)
    return row


def main():
    if (OUT/'result.json').exists():
        raise RuntimeError('Completed version exists; use a new version directory')
    OUT.mkdir(parents=True,exist_ok=True)
    raw,source,digest=load_rows();days=parse_days(raw,delay_minutes=0)
    prices,price_hash=audited_csv('data/processed/team_delivery/day_base.csv')
    price=np.array([float(r['price']) for r in prices])
    pvrows,pvhash=audited_csv('data/processed/team_delivery/pv_forecast.csv')
    published=parse_forecasts(pvrows)
    frozen=json.loads((MARGIN/'frozen_selection.json').read_text())
    margin_result=json.loads((MARGIN/'result.json').read_text())
    margin_check=json.loads((MARGIN/'independent_validation.json').read_text())
    if not margin_check['passed'] or margin_check['result_sha256']!=sha(MARGIN/'result.json') or margin_result['frozen_selection_sha256']!=sha(MARGIN/'frozen_selection.json'):
        raise ValueError('Q2 frozen candidate lacks current validation')
    config=MarginConfig(**frozen['selection']['config'])
    base_report=json.loads((BASE/'result.json').read_text())
    if sha(BASE/'B0.jsonl')!=base_report['strategies']['B0']['daily_file_sha256']:
        raise ValueError('Warmup changed')
    warmup=[json.loads(l) for l in (BASE/'B0.jsonl').open()][:31]
    initial=warmup[-1]['terminal_energy_kwh']
    protocol={'policy':POLICY,'variants':VARIANTS,'margin_config':frozen['selection']['config'],
        'margin_source':'Q2 historical lag7-load/lag1-PV residual bank; fixed midnight margin held all day',
        'scope':'transfer test; no Q3-specific residual fitting or February-December retuning',
        'q2_frozen_selection_sha256':sha(MARGIN/'frozen_selection.json'),
        'refund':'refund original cancelled cost plus50% penalty; relative to current commitment',
        'updates':[6,12,18],'conversion':'linear','terminal':'daily6000','efficiency':'.9 each',
        'power_side':'bus','warmup_B0_sha256':sha(BASE/'B0.jsonl'),
        'warmup':'reuse strict Q2 Jan1-31; common actual end state; Q3 experiment deployed Feb1'}
    dump(OUT/'protocol.json',protocol);protocol_hash=sha(OUT/'protocol.json')
    states=dict.fromkeys(VARIANTS,initial)
    totals={name:empty_summary() for name in VARIANTS}
    for v in totals.values():v.update(replan_attempts=0,material_revisions=0,increase_kwh=0.,decrease_kwh=0.)
    files={name:(OUT/f'{name}.jsonl').open('w') for name in VARIANTS}
    daily=[];selected={name:{} for name in VARIANTS};started=time.monotonic()
    try:
        for i in range(31,365):
            prediction,sources=forecast_actual_history(days,i,{'load':'last_week','pv':'yesterday'})
            enhanced,_,audit=corrected(days,i,config)
            zero_pv=published[midnight(days[i].day)].energy(decision_time=midnight(days[i].day),method='linear')
            plans={group:make_plan({'load':p['load'],'pv':zero_pv},price)
                   for group,p in [('base',prediction),('margin',enhanced)]}
            for name,(margin,control) in VARIANTS.items():
                before=time.monotonic()
                row=execute_day(days[i],price,enhanced if margin else prediction,sources,
                    plans['margin' if margin else 'base'],published,states[name],control)
                row.update(strategy=name,margin=audit if margin else None,
                    protocol_sha256=protocol_hash,runtime_seconds=time.monotonic()-before)
                states[name]=row['terminal_energy_kwh']
                files[name].write(json.dumps(row)+'\n')
                accumulate(totals[name],row)
                for revision in row['revisions']:
                    totals[name]['replan_attempts']+=1
                    totals[name]['material_revisions']+=int(max(revision['increase_kwh'],revision['decrease_kwh'])>1e-5)
                    for key in ('increase_kwh','decrease_kwh'):totals[name][key]+=revision[key]
                daily.append({'day':row['day'],'strategy':name,**row['costs']})
                if row['day'] in ('2025-03-20','2025-06-21','2025-09-23','2025-12-21'):
                    selected[name][row['day']]=row
            if (i-30)%60==0:print(i-30,'/334',round(time.monotonic()-started,1),'s',flush=True)
    finally:
        for f in files.values():f.close()
    hashes={str(source.relative_to(ROOT)):digest,'data/processed/team_delivery/day_base.csv':price_hash,
            'data/processed/team_delivery/pv_forecast.csv':pvhash}
    if any(sha(ROOT/p)!=h for p,h in hashes.items()) or sha(OUT/'protocol.json')!=protocol_hash:
        raise ValueError('Input/protocol changed')
    for name in totals:totals[name]['daily_file_sha256']=sha(OUT/f'{name}.jsonl')
    with (OUT/'daily_fees.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(daily[0]));w.writeheader();w.writerows(daily)
    dump(OUT/'selected_days.json',selected)
    dump(OUT/'result.json',{'status':'awaiting_independent_validation','strategies':totals,
        'input_sha256':hashes,'protocol_sha256':protocol_hash,'policy':POLICY,
        'evaluation_start':'2025-02-01','evaluation_end':'2025-12-31','days':334,
        'initial_energy_kwh':initial,'code_sha256':{str(p.relative_to(ROOT)):sha(p) for p in
        [Path(__file__).resolve(),ROOT/'scripts/run_strict_q2.py',ROOT/'scripts/run_q2_margin_oracle.py',
         ROOT/'scripts/run_real_q23.py',ROOT/'scripts/run_real_q2_forecast.py',*sorted((ROOT/'src').rglob('*.py'))]}})
    print({name:v['costs'] for name,v in totals.items()},flush=True)


if __name__=='__main__':main()
