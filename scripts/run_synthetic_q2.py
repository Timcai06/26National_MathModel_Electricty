"""Synthetic walk-forward evidence and forecast-to-kernel smoke test."""
from dataclasses import asdict
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from src.core import BatteryParams
from src.q2.forecast import ActualDay, history_as_of, midnight, predict_day
from src.q2.backtest import walk_forward
from src.q2.dispatch import plan_from_forecast


def main():
    start = date(2026,1,1)
    hours = np.arange(144)/6
    days = []
    for i in range(45):
        day = start+timedelta(days=i)
        load = 150+20*np.sin(hours*np.pi/12)+5*day.weekday()+i*.2
        pv = np.maximum(0,np.sin((hours-6)*np.pi/12))*100*(1+.02*day.weekday())
        days.append(ActualDay(day,load,pv,midnight(day)+timedelta(days=1)))
    metadata = dict(input_kind='synthetic',data_version='weekly-trend-45days-v1',
                    mapping_version='synthetic-midnight-144-v1',assumptions_version='day-end-available-v1')
    report = walk_forward(days,start_day=date(2026,2,1),end_day=date(2026,2,14),metadata=metadata)
    target = date(2026,2,1)
    forecast = predict_day(history_as_of(days,midnight(target)),target_day=target,method='last_week')
    result = plan_from_forecast(forecast,price_yuan_per_kwh=np.full(144,.5),price_available_at=midnight(target),
        battery_params=BatteryParams(.9,.9,'bus'),initial_energy_kwh=6000,terminal_energy_kwh=6000)
    if report['status'] != 'complete' or result.status != 'optimal' or not result.diagnostics['passed']:
        raise RuntimeError('Synthetic forecast/planning failed')
    output = ROOT/'analysis/synthetic_q2'
    output.mkdir(parents=True,exist_ok=True)
    bundle = {'scope':'synthetic-only; forecast accuracy and planning feasibility, not Q2 realized cost',
              'report':report, 'planning_example':asdict(result),
              'planning_configuration':{'price_yuan_per_kwh':.5,'eta_charge':.9,'eta_discharge':.9,
                 'power_reference_side':'bus','initial_kwh':6000,'terminal_kwh':6000,'method':'last_week','day':str(target)},
              'code_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in [Path(__file__).resolve(),*sorted((ROOT/'src').rglob('*.py'))]}}
    (output/'result.json').write_text(json.dumps(bundle,ensure_ascii=False,indent=2,
        default=lambda x:x.tolist() if isinstance(x,np.ndarray) else str(x))+'\n')
    print(json.dumps(report['summary'],indent=2))
    print('Forecast-only planned cost:',result.objective_yuan,'yuan; NOT realized cost')


if __name__ == '__main__':
    main()
