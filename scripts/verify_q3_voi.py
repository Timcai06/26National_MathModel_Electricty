"""Independent as-of scenarios, gate economics, January selection and execution."""
from dataclasses import asdict
from datetime import date,timedelta
from pathlib import Path
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from scripts.run_q3_voi import OUT,CONTROL,MARGIN
from scripts.run_q2_margin_oracle import sha,make_plan
from scripts.run_real_q23 import audited_csv,dump,BATTERY
from scripts.run_real_q2_forecast import load_rows,parse_days
from scripts.verify_real_q23 import check_day
from scripts.verify_q2_margin_oracle import check_margin
from src.q2.forecast import midnight
from src.q3.pv import parse_forecasts
from src.q3.strict_execution import StrictRollingExecutor
from src.q3.voi import CANDIDATES,GateConfig,evaluate


def independent_scenarios(day,slot,by_day,published,baseline_load):
    start=midnight(day);decision=start+timedelta(minutes=slot*10)
    dates=[]
    for offset in range(28,0,-1):
        d=day-timedelta(days=offset);source=d-timedelta(days=7)
        if d not in by_day or source not in by_day:continue
        if by_day[d].available_at>start or by_day[source].available_at>midnight(d):continue
        dates.append(d)
    dates=dates[-20:]
    pnow=published[decision].energy(decision_time=decision,method='linear')[:144-slot]
    loads=[];pvs=[];provenance=[];clipped=0
    for d in dates:
        source=d-timedelta(days=7);past_issue=midnight(d)+timedelta(minutes=slot*10)
        ppast=published[past_issue].energy(decision_time=past_issue,method='linear')[:144-slot]
        l=baseline_load[slot:]+(by_day[d].load_kwh[slot:]-by_day[source].load_kwh[slot:])
        p=pnow+(by_day[d].pv_kwh[slot:]-ppast)
        clipped+=int((l<0).sum()+(p<0).sum());loads.append(np.maximum(l,0.));pvs.append(np.maximum(p,0.))
        provenance.append({'day':str(d),'available_at':by_day[d].available_at.isoformat(),
            'load_source_day':str(source),'pv_issue_time':past_issue.isoformat()})
    return np.asarray(loads),np.asarray(pvs),provenance,clipped


def check_actions_and_gates(row,days,by_day,published,price,margin,config):
    day=date.fromisoformat(row['day']);start=midnight(day)
    check_margin(row,by_day,margin)
    baseline_load=by_day[day-timedelta(days=7)].load_kwh
    load=baseline_load+np.asarray(row['margin']['correction_kwh'])
    pv=published[start].energy(decision_time=start,method='linear')
    planned=make_plan({'load':load,'pv':pv},price)
    if not np.allclose(planned,row['planned_G'],atol=1e-6,rtol=0):raise ValueError('Initial plan mismatch')
    c=StrictRollingExecutor(day=day,commitment=row['planned_G'],price=price,forecast_load=load,forecast_pv=pv,
        forecast_available_at=start,battery=BATTERY,initial_energy=row['initial_energy_kwh'])
    history=[d for d in days if d.day<day]
    if [g['first_slot'] for g in row['gates']]!=[36,72,108] or len(row['commands'])!=144:raise ValueError('Gate/command coverage mismatch')
    revision_index=0
    for slot in range(144):
        decision=start+timedelta(minutes=10*slot)
        if slot in (36,72,108):
            saved=row['gates'][slot//36-1]
            as_of={k:v for k,v in published.items() if k<=decision}
            proposal,audit,previews=evaluate(c,decision_time=decision,published_as_of=as_of,
                history=history,baseline_load=baseline_load,config=config)
            clean={k:v for k,v in saved.items() if not k.startswith('posthoc_')}
            if audit!=clean:raise ValueError('Gate depends on actuals or different frozen data')
            loads,pvs,provenance,clipped=independent_scenarios(day,slot,by_day,published,baseline_load)
            if provenance!=saved['scenario']['scenario_days'] or clipped!=saved['scenario']['clipped_negative_points'] or len(provenance)!=saved['scenario']['scenario_count']:
                raise ValueError('Historical scenario membership mismatch')
            digest=hashlib.sha256(loads.tobytes()+pvs.tobytes()).hexdigest()
            if digest!=saved['scenario']['scenario_sha256']:raise ValueError('Scenario numerical mismatch')
            keep,update=previews
            old=c.g[slot:];new=proposal['commitment'][slot:];delta=new-old
            adjustment=float(price[slot:]@(1.5*np.maximum(delta,0)-.5*np.maximum(-delta,0)))
            if abs(adjustment-saved['adjustment_yuan'])>1e-6:raise ValueError('Adjustment fee mismatch')
            values=[]
            for schedule,extra in [(keep,0.),(update,adjustment)]:
                u=np.maximum(loads+schedule['C']-schedule['G']-pvs-schedule['D'],0.)
                values.append(u@(5*price[slot:])+extra)
            for expected,key in zip(values,['keep_scenario_costs','update_scenario_costs']):
                if not np.allclose(expected,saved[key],atol=1e-6,rtol=0):raise ValueError('Scenario fee mismatch')
            gain=float(values[0].mean()-values[1].mean())
            if abs(gain-saved['predicted_gain_yuan'])>1e-6 or saved['accept']!=(config.enabled and gain>config.threshold_yuan+1e-6):raise ValueError('Gate acceptance mismatch')
            for schedule,extra,key in [(keep,0.,'posthoc_keep_variable_yuan'),(update,adjustment,'posthoc_update_variable_yuan')]:
                actual=by_day[day]
                u=np.maximum(actual.load_kwh[slot:]+schedule['C']-schedule['G']-actual.pv_kwh[slot:]-schedule['D'],0.)
                if abs(float(u@(5*price[slot:])+extra)-saved[key])>1e-6:raise ValueError('Posthoc fee mismatch')
            if saved['accept']:
                if proposal['revision']!=row['revisions'][revision_index]:raise ValueError('Accepted proposal not committed')
                revision_index+=1
                c.revise(commitment=proposal['commitment'],remaining_load=c.load[slot:],remaining_pv=proposal['remaining_pv'],
                         decision_time=decision,forecast_available_at=decision)
        command=c.decide(decision)
        if asdict(command)!=row['commands'][slot]:raise ValueError('Command depends on actual truth')
        for key in ('G','C','D'):
            value=c.g[slot] if key=='G' else getattr(command,key)
            if value!=row['schedule'][key][slot]:raise ValueError('Recorded schedule differs from commands')
        c.settle(load_kwh=0.,pv_kwh=0.,available_at=decision+timedelta(minutes=10))
    if revision_index!=len(row['revisions']):raise ValueError('Unapproved contract changes')


def main():
    report=json.loads((OUT/'result.json').read_text());protocol=json.loads((OUT/'protocol.json').read_text())
    frozen=json.loads((OUT/'frozen_selection.json').read_text())
    for p,h in {**report['input_sha256'],**report['code_sha256']}.items():
        if sha(ROOT/p)!=h:raise ValueError('Input/code changed: '+p)
    if (sha(OUT/'protocol.json')!=report['protocol_sha256'] or sha(OUT/'frozen_selection.json')!=report['frozen_selection_sha256'] or
        sha(OUT/'january_development.jsonl')!=frozen['january_trace_sha256'] or sha(CONTROL/'result.json')!=protocol['fixed_control_result_sha256'] or
        sha(MARGIN/'frozen_selection.json')!=protocol['parameter_source_sha256']):raise ValueError('Frozen artifact changed')
    raw,_,_=load_rows();days=parse_days(raw,delay_minutes=0);by_day={d.day:d for d in days}
    pr,_=audited_csv('data/processed/team_delivery/day_base.csv');price=np.array([float(r['price']) for r in pr])
    pvrows,_=audited_csv('data/processed/team_delivery/pv_forecast.csv');published=parse_forecasts(pvrows)
    totals={i:0. for i in range(5)};states=dict.fromkeys(totals,6000.);seen=set();jan_accepted=dict.fromkeys(totals,0)
    for line in (OUT/'january_development.jsonl').open():
        row=json.loads(line);day=date.fromisoformat(row['day']);cid=row['candidate_id']
        if cid not in totals or not date(2025,1,15)<=day<=date(2025,1,31) or (cid,day) in seen:raise ValueError('January coverage mismatch')
        seen.add((cid,day));states[cid],_,fee=check_day(row,by_day[day],price,states[cid],True)
        check_actions_and_gates(row,days,by_day,published,price,protocol['margin_config'],CANDIDATES[cid])
        totals[cid]+=fee['total_yuan'];jan_accepted[cid]+=len(row['revisions'])
    if len(seen)!=85:raise ValueError('Incomplete calibration')
    for score in frozen['scores']:
        cid=score['candidate_id']
        if abs(totals[cid]-score['cost_yuan'])>1e-5 or jan_accepted[cid]!=score['accepted_updates'] or score['config']!=asdict(CANDIDATES[cid]):raise ValueError('January score mismatch')
    chosen=min(totals,key=lambda c:(totals[c],c))
    if frozen['selected']['candidate_id']!=chosen:raise ValueError('Wrong January selection')
    config=CANDIDATES[chosen];print('January freeze verified',flush=True)
    path=OUT/'adaptive.jsonl';expected=report['strategies']['adaptive']
    if sha(path)!=expected['daily_file_sha256']:raise ValueError('Adaptive trace changed')
    rows=[json.loads(l) for l in path.open()]
    if len(rows)!=334:raise ValueError('Missing evaluation dates')
    control_report=json.loads((CONTROL/'result.json').read_text())
    cp=CONTROL/'margin_zero.jsonl'
    if sha(cp)!=control_report['strategies']['margin_zero']['daily_file_sha256']:raise ValueError('Fixed control changed')
    fixed=[json.loads(l) for l in cp.open()]
    state=report['initial_energy_kwh'];fees=dict.fromkeys(expected['costs'],0.);months={};worst=0.
    counts={'accepted_updates':0,'evaluated_updates':0,'material_updates':0,'increase_kwh':0.,'decrease_kwh':0.}
    for index,row in enumerate(rows,31):
        if row['frozen_selection_sha256']!=report['frozen_selection_sha256'] or row['protocol_sha256']!=report['protocol_sha256']:raise ValueError('Policy not frozen')
        state,residual,fee=check_day(row,days[index],price,state,True);worst=max(worst,residual)
        check_actions_and_gates(row,days,by_day,published,price,protocol['margin_config'],config)
        if not np.array_equal(row['planned_G'],fixed[index-31]['planned_G']):raise ValueError('Adaptive initial G differs from fixed baseline')
        for k,v in fee.items():fees[k]+=v
        month=row['day'][:7];months[month]=months.get(month,0.)+fee['total_yuan']
        counts['evaluated_updates']+=3;counts['accepted_updates']+=len(row['revisions'])
        for r in row['revisions']:
            counts['material_updates']+=int(max(r['increase_kwh'],r['decrease_kwh'])>1e-5)
            for k in ('increase_kwh','decrease_kwh'):counts[k]+=r[k]
    if (any(abs(fees[k]-expected['costs'][k])>1e-5 for k in fees) or set(months)!=set(expected['monthly_total_yuan']) or
        any(abs(v-expected['monthly_total_yuan'][k])>1e-5 for k,v in months.items()) or any(abs(v-expected[k])>1e-5 for k,v in counts.items())):raise ValueError('Evaluation summary mismatch')
    dump(OUT/'independent_validation.json',{'passed':True,'january_traces_verified':85,'evaluation_days_verified':334,
        'gates_verified':3*(85+334),'max_physical_residual_kwh':worst,'costs':fees,
        'scenarios_and_adjustment_fees_recomputed':True,'zero_actual_decisions_identical':True,
        'posthoc_values_excluded_from_decisions':True,'same_initial_G_as_margin_zero':True,
        'result_sha256':sha(OUT/'result.json'),'verifier_sha256':sha(Path(__file__).resolve())})
    print('Independent VOI verification passed:85 January +334 evaluation days,1257 gates')


if __name__=='__main__':main()
