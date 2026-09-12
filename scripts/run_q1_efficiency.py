"""Controlled efficiency interpretation comparison on audited real Q1 data."""
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from run_real_q1 import load_inputs
from run_q1_comparison import encode
from src.core import BatteryParams
from src.q1.compare import compare_q1_strategies


def main():
    base,source,digest=load_inputs()
    reports={}
    rows=[]
    for name,eta in [('each_direction_90',.9),('round_trip_90',math.sqrt(.9))]:
        inputs={**base,'battery_params':BatteryParams(eta,eta,'bus'),
                'input_metadata':{**base['input_metadata'],'assumptions_version':name+'-bus-neutral6000-candidate-v1'}}
        report=compare_q1_strategies(**inputs)
        if report['status']!='passed':raise RuntimeError(name+' comparison failed')
        reports[name]={'input':inputs,'comparison':report}
        for row in report['summary']:
            rows.append({'efficiency_case':name,'eta_charge':eta,'eta_discharge':eta,'round_trip':eta*eta,**row})
    a,b=[reports[k]['comparison']['strategies']['optimized'] for k in reports]
    if b.objective_yuan>a.objective_yuan+1e-6:raise RuntimeError('Higher-efficiency optimal cost unexpectedly worse')
    normal=[r['cost_yuan'] for r in rows if r['strategy']=='no_storage']
    if abs(normal[0]-normal[1])>1e-6:raise RuntimeError('No-storage control changed')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=digest:raise RuntimeError('Input changed')
    delta=a.objective_yuan-b.objective_yuan
    output=ROOT/'analysis/q1_efficiency'
    output.mkdir(parents=True,exist_ok=True)
    bundle={'scope':'real-data sensitivity, not evidence of intended problem interpretation',
        'source_sha256':digest,'reports':reports,'optimal_cost_reduction_yuan':delta,
        'optimal_cost_reduction_fraction':delta/a.objective_yuan,
        'code_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__).resolve(),ROOT/'scripts/run_real_q1.py',*sorted((ROOT/'src').rglob('*.py'))]}}
    (output/'result.json').write_text(json.dumps(bundle,default=encode,ensure_ascii=False,indent=2)+'\n')
    with (output/'summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps(rows,indent=2))
    print('Optimal cost reduction:',delta,'yuan;',delta/a.objective_yuan*100,'%')


if __name__=='__main__':main()
