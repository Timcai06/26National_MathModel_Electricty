"""Multi-day synthetic comparison, with historical and physical warmup explicit."""
from datetime import date,timedelta
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from src.core import BatteryParams
from src.q2.forecast import ActualDay,midnight
from src.q2.coordinator import PriceDay,compare_multiday
from src.q2.execution import OBSERVATION_POLICY


def main():
    start=date(2026,1,1)
    hours=np.arange(144)/6
    days=[]
    for i in range(45):
        day=start+timedelta(days=i)
        load=150+20*np.sin(hours*np.pi/12)+5*day.weekday()+i*.2
        pv=np.maximum(0,np.sin((hours-6)*np.pi/12))*100*(1+.02*day.weekday())
        days.append(ActualDay(day,load,pv,midnight(day)+timedelta(days=1)))
    prices=[PriceDay(d.day,np.full(144,.5),midnight(d.day)) for d in days]
    report=compare_multiday(days,prices,simulation_start=date(2026,1,8),evaluation_start=date(2026,2,1),
        end_day=date(2026,2,14),initial_energy_kwh=6000,initial_state_source='Synthetic Jan 8 initial state; no claim of Jan 1 physical warmup',
        battery_params=BatteryParams(.9,.9,'bus'),terminal_policy='daily_neutral',emergency_multiplier=5,
        observation_policy=OBSERVATION_POLICY,metadata=dict(input_kind='synthetic',data_version='weekly-trend-45days-v1',
            mapping_version='synthetic-midnight-144-v1',assumptions_version='slot-observable-daily-neutral-v1'))
    if report['status']!='complete' or not report['cost_comparison_valid']:raise RuntimeError('Comparison incomplete')
    output=ROOT/'analysis/q2_multiday'
    output.mkdir(parents=True,exist_ok=True)
    bundle={'report':report,'code_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__).resolve(),*sorted((ROOT/'src').rglob('*.py'))]}}
    def encode(v):
        if isinstance(v,np.ndarray):return v.tolist()
        if isinstance(v,(date,)):return v.isoformat()
        raise TypeError(type(v))
    (output/'result.json').write_text(json.dumps(bundle,default=encode,ensure_ascii=False,indent=2)+'\n')
    summary={k:v['summary'] for k,v in report['strategies'].items()}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
