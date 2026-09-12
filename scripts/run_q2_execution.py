"""Synthetic forecast -> locked commitment -> causal execution -> settlement."""
from dataclasses import asdict
from datetime import date,timedelta
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from src.core import BatteryParams
from src.q2.forecast import ActualDay,midnight,predict_day
from src.q2.dispatch import plan_from_forecast
from src.q2.execution import CausalExecutor,OBSERVATION_POLICY


def main():
    day=date(2026,2,1)
    battery=BatteryParams(.9,.9,'bus')
    forecast=predict_day([ActualDay(day-timedelta(days=1),np.full(144,100),np.full(144,20),midnight(day))],
                         target_day=day,method='yesterday')
    price=np.full(144,.5)
    plan=plan_from_forecast(forecast,price_yuan_per_kwh=price,price_available_at=midnight(day),
        battery_params=battery,initial_energy_kwh=6000,terminal_energy_kwh=6000)
    if plan.status!='optimal' or not plan.diagnostics['passed']:raise RuntimeError('Planning failed')
    reports={}
    for name,load,pv,target in [('matched',100,20,6000),('shortfall_neutral',150,10,6000),
                               ('shortfall_free',150,10,None),('surplus_neutral',50,200,6000)]:
        e=CausalExecutor(day=day,commitment_kwh=plan.schedule['G'],price_yuan_per_kwh=price,
            price_available_at=midnight(day),battery_params=battery,initial_energy_kwh=6000,
            terminal_energy_kwh=target,emergency_multiplier=5,observation_policy=OBSERVATION_POLICY)
        for i in range(144):
            e.step(slot_id=i,load_kwh=load,pv_kwh=pv,available_at=midnight(day)+timedelta(minutes=10*(i+1)))
        report=e.finish()
        if report['status']!='validated':raise RuntimeError(name+' failed physics')
        reports[name]=report
        print(name,report['costs'],'terminal_kwh=',e.energy_kwh)
    output=ROOT/'analysis/q2_execution'
    output.mkdir(parents=True,exist_ok=True)
    bundle={'scope':'synthetic only; online within-slot observability and recourse assumptions unaccepted',
        'forecast':asdict(forecast),'plan':asdict(plan),'battery_params':asdict(battery),
        'price_yuan_per_kwh':price,'reports':reports,
        'code_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in [Path(__file__).resolve(),*sorted((ROOT/'src').rglob('*.py'))]}}
    (output/'result.json').write_text(json.dumps(bundle,ensure_ascii=False,indent=2,
        default=lambda v:v.tolist() if isinstance(v,np.ndarray) else v.isoformat())+'\n')


if __name__=='__main__':main()
