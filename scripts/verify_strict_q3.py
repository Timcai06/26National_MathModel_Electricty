"""Independent Q3 ledgers, forecast chronology, margins and zero-truth replay."""
from pathlib import Path
from datetime import date,timedelta
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from scripts.run_strict_q3 import OUT,VARIANTS,execute_day,MARGIN,BASE
from scripts.run_q2_margin_oracle import sha,make_plan
from scripts.run_real_q23 import audited_csv,dump
from scripts.run_real_q2_forecast import load_rows,parse_days
from scripts.verify_real_q23 import check_day
from scripts.verify_q2_margin_oracle import check_margin
from src.q2.forecast import ActualDay,midnight
from src.q3.pv import parse_forecasts


def main():
    report=json.loads((OUT/'result.json').read_text())
    protocol=json.loads((OUT/'protocol.json').read_text())
    if sha(OUT/'protocol.json')!=report['protocol_sha256'] or sha(MARGIN/'frozen_selection.json')!=protocol['q2_frozen_selection_sha256'] or sha(BASE/'B0.jsonl')!=protocol['warmup_B0_sha256']:
        raise ValueError('Protocol/parameter/warmup mismatch')
    for p,h in {**report['input_sha256'],**report['code_sha256']}.items():
        if sha(ROOT/p)!=h:raise ValueError('Input/code changed: '+p)
    raw,_,_=load_rows();days=parse_days(raw,delay_minutes=0);by_day={d.day:d for d in days}
    prices,_=audited_csv('data/processed/team_delivery/day_base.csv');price=np.array([float(r['price']) for r in prices])
    pvrows,_=audited_csv('data/processed/team_delivery/pv_forecast.csv');published=parse_forecasts(pvrows)
    evidence={};initial_plans={}
    for name,(margin,control) in VARIANTS.items():
        path=OUT/f'{name}.jsonl';expected=report['strategies'][name]
        if sha(path)!=expected['daily_file_sha256']:raise ValueError('Trace changed')
        rows=[json.loads(line) for line in path.open()]
        if len(rows)!=334:raise ValueError('Missing dates')
        state=report['initial_energy_kwh'];costs=dict.fromkeys(expected['costs'],0.);months={};worst=0.
        counts={'replan_attempts':0,'material_revisions':0,'increase_kwh':0.,'decrease_kwh':0.}
        quantities=dict.fromkeys(('emergency_kwh','surplus_kwh','charge_kwh','discharge_kwh'),0.)
        for index,row in enumerate(rows,31):
            day=days[index].day;start=midnight(day)
            state,residual,fee=check_day(row,days[index],price,state,True);worst=max(worst,residual)
            if row['policy']!=report['policy'] or row['control']!=control or row['protocol_sha256']!=report['protocol_sha256']:
                raise ValueError('Policy drift')
            if margin:
                check_margin(row,by_day,protocol['margin_config'])
                # Independent residual arithmetic can differ by an ulp. After
                # verifying the saved correction within tolerance, replay the
                # EXACT original forecast bytes to isolate actual-data effects.
                load=by_day[day-timedelta(days=7)].load_kwh+np.asarray(row['margin']['correction_kwh'])
            else:
                if row['margin'] is not None:raise ValueError('Base control has margin')
                load=by_day[day-timedelta(days=7)].load_kwh
            forecast={'load':load,'pv':published[start].energy(decision_time=start,method='linear')}
            optimal_plan=make_plan(forecast,price)
            if not np.allclose(optimal_plan,row['planned_G'],atol=1e-6,rtol=0):
                raise ValueError('Midnight plan not generated from declared forecast')
            group='margin' if margin else 'base';key=(group,day)
            if key not in initial_plans:initial_plans[key]=row['planned_G']
            elif not np.array_equal(initial_plans[key],row['planned_G']):
                raise ValueError('Paired controls start with different contracts')
            expected_slots=[] if control=='zero' else [36,72,108]
            if [r['first_slot'] for r in row['revisions']]!=expected_slots:
                raise ValueError('Missing/extra contract updates')
            for r in row['revisions']:
                required=start+timedelta(minutes=10*r['first_slot']) if control=='fresh' else start
                if r['forecast_issue_time']!=required.isoformat():raise ValueError('Wrong forecast issue')
                delta=np.asarray(r['new_remaining_kwh'])-r['old_remaining_kwh']
                up,down=float(np.maximum(delta,0).sum()),float(np.maximum(-delta,0).sum())
                if max(abs(up-r['increase_kwh']),abs(down-r['decrease_kwh']))>1e-6:
                    raise ValueError('Revision volumes mismatch')
                counts['replan_attempts']+=1;counts['material_revisions']+=int(max(up,down)>1e-5)
                counts['increase_kwh']+=up;counts['decrease_kwh']+=down
            zero_actual=ActualDay(day,np.zeros(144),np.zeros(144),start+timedelta(days=1))
            replay=execute_day(zero_actual,price,forecast,row['forecast_sources'],np.asarray(row['planned_G']),
                               published,row['initial_energy_kwh'],control)
            if replay['commands']!=row['commands'] or replay['revisions']!=row['revisions']:
                raise ValueError('Battery/contract decisions depend on actual truth')
            for k in ('G','C','D','E'):
                if not np.array_equal(replay['schedule'][k],row['schedule'][k]):
                    raise ValueError('Executed decisions differ from zero-truth replay')
            for k,v in fee.items():costs[k]+=v
            for key,variable in [('emergency_kwh','U'),('surplus_kwh','W'),('charge_kwh','C'),('discharge_kwh','D')]:
                quantities[key]+=sum(row['schedule'][variable])
            month=str(day)[:7];months[month]=months.get(month,0.)+fee['total_yuan']
        if (any(abs(costs[k]-expected['costs'][k])>1e-5 for k in costs) or
            set(months)!=set(expected['monthly_total_yuan']) or
            any(abs(v-expected['monthly_total_yuan'][k])>1e-5 for k,v in months.items()) or
            any(abs(v-expected[k])>1e-5 for k,v in {**counts,**quantities}.items())):
            raise ValueError('Summary mismatch')
        evidence[name]={'days_verified':334,'max_physical_residual_kwh':worst,'costs':costs,
                        'zero_truth_actions_and_contracts_identical':True,'passed':True}
        print('Verified',name,flush=True)
    dump(OUT/'independent_validation.json',{'passed':True,'strategies':evidence,
        'days_verified':2004,'slots_verified':2004*144,'same_initial_contract_within_each_group':True,
        'q2_parameters_unchanged':True,'result_sha256':sha(OUT/'result.json'),'verifier_sha256':sha(Path(__file__).resolve())})
    print('Independent Q3 transfer verification passed:2004 days,288576 slots')


if __name__=='__main__':main()
