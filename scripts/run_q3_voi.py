"""January-selected paired-scenario gate; preserve prior fixed controls."""
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
import csv
import json
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from scripts.run_strict_q3 import OUT as CONTROL
from scripts.run_q2_margin_oracle import sha,make_plan,corrected,empty_summary,accumulate,OUT as MARGIN
from scripts.run_real_q23 import audited_csv,dump,BATTERY
from scripts.run_real_q2_forecast import load_rows,parse_days
from src.q2.forecast import midnight
from src.q2.residual_margin import MarginConfig
from src.q3.strict_execution import StrictRollingExecutor
from src.q3.pv import parse_forecasts
from src.q3.voi import CANDIDATES,GateConfig,evaluate,variable_cost

OUT=ROOT/'analysis/q3_voi_v1'


def execute_day(actual,price,prediction,sources,commitment,published,history,baseline_load,initial,config):
    start=midnight(actual.day)
    initial_pv=published[start].energy(decision_time=start,method='linear')
    executor=StrictRollingExecutor(day=actual.day,commitment=commitment,price=price,forecast_load=prediction['load'],
        forecast_pv=initial_pv,forecast_available_at=start,battery=BATTERY,initial_energy=initial)
    revisions=[];gates=[];posthoc=[]
    for slot in range(144):
        decision=start+timedelta(minutes=10*slot)
        if slot in (36,72,108):
            as_of={issue:f for issue,f in published.items() if issue<=decision}
            proposal,audit,previews=evaluate(executor,decision_time=decision,published_as_of=as_of,
                history=history,baseline_load=baseline_load,config=config)
            gates.append(audit);posthoc.append(previews)
            if audit['accept']:
                executor.revise(commitment=proposal['commitment'],remaining_load=executor.load[slot:],
                    remaining_pv=proposal['remaining_pv'],decision_time=decision,forecast_available_at=decision)
                revisions.append(proposal['revision'])
        executor.decide(decision)
        executor.settle(load_kwh=float(actual.load_kwh[slot]),pv_kwh=float(actual.pv_kwh[slot]),available_at=decision+timedelta(minutes=10))
    result=executor.finish()
    base=float(price@commitment);adjust=sum(r['incremental_cost_yuan'] for r in revisions)
    penalty=sum(float(.5*price[r['first_slot']:]@np.abs(np.asarray(r['new_remaining_kwh'])-r['old_remaining_kwh'])) for r in revisions)
    ledger=abs(base+adjust-float(price@executor.g)-penalty)
    if ledger>1e-6:raise ValueError('Adaptive ledger mismatch')
    result['costs'].update(planned_yuan=base,adjustment_yuan=adjust,total_yuan=base+adjust+result['costs']['emergency_yuan'])
    # End-of-day diagnostics only; these actuals never reach evaluate().
    for audit,previews in zip(gates,posthoc):
        if previews is None:continue
        slot=audit['first_slot']
        audit['posthoc_keep_variable_yuan']=float(variable_cost(previews[0],actual.load_kwh[slot:],actual.pv_kwh[slot:],price[slot:]))
        audit['posthoc_update_variable_yuan']=float(variable_cost(previews[1],actual.load_kwh[slot:],actual.pv_kwh[slot:],price[slot:])+audit['adjustment_yuan'])
        audit['posthoc_scope']='frozen-continuation counterfactual; not adaptive final realized continuation'
    result.update(day=str(actual.day),initial_energy_kwh=initial,terminal_energy_kwh=executor.energy,
        forecast_sources=sources,planned_G=commitment.tolist(),revisions=revisions,pv_issue_time=start.isoformat(),
        gates=gates,ledger_residual_yuan=ledger,control='adaptive_voi')
    return result


def day_inputs(days,index,margin,published,price):
    prediction,sources,audit=corrected(days,index,margin)
    start=midnight(days[index].day)
    g=make_plan({'load':prediction['load'],'pv':published[start].energy(decision_time=start,method='linear')},price)
    return prediction,sources,audit,g,days[index-7].load_kwh


def select_config(january,published,price,margin):
    if len(january)!=31 or any(d.day.month!=1 for d in january):raise ValueError('January-only calibration required')
    published={issue:f for issue,f in published.items() if issue<midnight(january[-1].day)+timedelta(days=1)}
    scores=[]
    with (OUT/'january_development.jsonl').open('w') as f:
        for cid,config in enumerate(CANDIDATES):
            total=0.;state=6000.;accepted=0
            for i in range(14,31):
                prediction,sources,audit,g,load=day_inputs(january,i,margin,published,price)
                row=execute_day(january[i],price,prediction,sources,g,published,january[:i],load,state,config)
                state=row['terminal_energy_kwh'];total+=row['costs']['total_yuan'];accepted+=len(row['revisions'])
                row.update(candidate_id=cid,margin=audit)
                f.write(json.dumps(row)+'\n')
            scores.append({'candidate_id':cid,'config':asdict(config),'cost_yuan':total,'accepted_updates':accepted})
            print('January candidate',scores[-1],flush=True)
    selected=min(scores,key=lambda x:(x['cost_yuan'],x['candidate_id']))
    dump(OUT/'frozen_selection.json',{'selected':selected,'scores':scores,
        'selection_available_at':'2025-02-01T00:00:00+08:00','evaluation':'retrospective Feb-Dec, not blind',
        'january_trace_sha256':sha(OUT/'january_development.jsonl')})
    return GateConfig(**selected['config'])


def main():
    if (OUT/'result.json').exists():raise RuntimeError('Completed version exists; use a new version')
    OUT.mkdir(parents=True,exist_ok=True)
    raw,source,digest=load_rows();days=parse_days(raw,delay_minutes=0)
    pr,ph=audited_csv('data/processed/team_delivery/day_base.csv');price=np.array([float(r['price']) for r in pr])
    pvrows,pvh=audited_csv('data/processed/team_delivery/pv_forecast.csv');published=parse_forecasts(pvrows)
    control=json.loads((CONTROL/'result.json').read_text());valid=json.loads((CONTROL/'independent_validation.json').read_text())
    if not valid['passed'] or valid['result_sha256']!=sha(CONTROL/'result.json'):raise ValueError('Fixed controls not validated')
    control_protocol=json.loads((CONTROL/'protocol.json').read_text())
    if sha(MARGIN/'frozen_selection.json')!=control_protocol['q2_frozen_selection_sha256']:raise ValueError('Margin changed')
    margin=MarginConfig(**control_protocol['margin_config'])
    dump(OUT/'protocol.json',{'candidates':[asdict(c) for c in CANDIDATES],
        'margin_config':asdict(margin),'training':['2025-01-15','2025-01-31'],
        'scenarios':'last20 eligible joint residual days within28days, minimum7; only completed days',
        'residuals':'lag7 load and matching-hour published PV; current scenarios centered at unmargined load and current PV',
        'continuation':'no future revisions in preview; greedy controls under candidate forecast; revisit next boundary',
        'keep':'retain contract AND current battery-control forecast',
        'fee':'existing contract sunk; update adjustment plus expected5p emergency, adjustment counted once',
        'numerical_gain_tolerance_yuan':1e-6,'fixed_control_result_sha256':sha(CONTROL/'result.json'),
        'parameter_source_sha256':sha(MARGIN/'frozen_selection.json')})
    protocol_hash=sha(OUT/'protocol.json')
    config=select_config(days[:31],published,price,margin)
    frozen_hash=sha(OUT/'frozen_selection.json');state=control['initial_energy_kwh']
    total=empty_summary();total.update(accepted_updates=0,evaluated_updates=0,material_updates=0,increase_kwh=0.,decrease_kwh=0.)
    daily=[];selected={};started=time.monotonic()
    with (OUT/'adaptive.jsonl').open('w') as f:
        for i in range(31,365):
            before=time.monotonic()
            prediction,sources,audit,g,load=day_inputs(days,i,margin,published,price)
            row=execute_day(days[i],price,prediction,sources,g,published,days[:i],load,state,config)
            row.update(margin=audit,strategy='adaptive',runtime_seconds=time.monotonic()-before,
                frozen_selection_sha256=frozen_hash,protocol_sha256=protocol_hash)
            state=row['terminal_energy_kwh'];accumulate(total,row)
            total['evaluated_updates']+=len(row['gates']);total['accepted_updates']+=len(row['revisions'])
            for r in row['revisions']:
                total['material_updates']+=int(max(r['increase_kwh'],r['decrease_kwh'])>1e-5)
                for k in ('increase_kwh','decrease_kwh'):total[k]+=r[k]
            daily.append({'day':row['day'],**row['costs'],'accepted_updates':len(row['revisions'])})
            if row['day'] in ('2025-03-20','2025-06-21','2025-09-23','2025-12-21'):selected[row['day']]=row
            f.write(json.dumps(row)+'\n')
            if (i-30)%60==0:print(i-30,'/334',round(time.monotonic()-started,1),'s',flush=True)
    hashes={str(source.relative_to(ROOT)):digest,'data/processed/team_delivery/day_base.csv':ph,'data/processed/team_delivery/pv_forecast.csv':pvh}
    if any(sha(ROOT/p)!=h for p,h in hashes.items()) or sha(OUT/'protocol.json')!=protocol_hash or sha(OUT/'frozen_selection.json')!=frozen_hash:raise ValueError('Inputs/protocol changed')
    total['daily_file_sha256']=sha(OUT/'adaptive.jsonl')
    with (OUT/'daily_fees.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(daily[0]));w.writeheader();w.writerows(daily)
    dump(OUT/'selected_days.json',selected)
    dump(OUT/'result.json',{'status':'awaiting_independent_validation','strategies':{'adaptive':total},
        'input_sha256':hashes,'protocol_sha256':protocol_hash,'frozen_selection_sha256':frozen_hash,
        'policy':control['policy'],'initial_energy_kwh':control['initial_energy_kwh'],
        'code_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),
        ROOT/'scripts/run_strict_q3.py',ROOT/'scripts/run_q2_margin_oracle.py',ROOT/'scripts/run_real_q23.py',
        ROOT/'scripts/run_strict_q2.py',ROOT/'scripts/run_real_q2_forecast.py',*sorted((ROOT/'src').rglob('*.py'))]}})
    print('Adaptive',total,flush=True)


if __name__=='__main__':main()
