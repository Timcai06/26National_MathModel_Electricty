"""Real Q1 candidate using an immutable, previously audited standardized CSV."""
import csv
from dataclasses import asdict
from datetime import date,datetime,timedelta
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from src.core import BatteryParams
from src.q1.compare import compare_q1_strategies
from src.q1.solve import prepare_q1_inputs
from src.q1.tables import TableTimeContract,ZONE,extract_q1_tables,render_q1_tables_markdown
from run_q1_comparison import encode
from run_q1_figures import draw_case


def load_inputs():
    source=ROOT/'data/processed/team_delivery/day_base.csv'
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    audit=json.loads((ROOT/'analysis/team_delivery/intake_audit.json').read_text())
    if audit['input_sha256'].get(str(source.relative_to(ROOT)))!=digest:
        raise ValueError('CSV changed since intake audit')
    if audit['source_comparisons']['day_base']['mismatches_above_1e-8'] != 0:
        raise ValueError('Source comparison failed')
    with source.open(newline='',encoding='utf-8-sig') as f: rows=list(csv.DictReader(f))
    if len(rows)!=144 or [int(r['slot']) for r in rows]!=list(range(144)):
        raise ValueError('Invalid slot order; no sorting or cleaning')
    for i,r in enumerate(rows):
        expected=(datetime(2000,1,1)+timedelta(minutes=10*(i+1))).strftime('%H:%M:%S') if i<143 else '0:00+1'
        if r['time'] not in ([expected,expected[:5]] if i<143 else [expected]):raise ValueError('Time label mismatch')
        for kw,kwh in [('load_kw','load_kwh'),('pv_forecast_kw','pv_forecast_kwh')]:
            if abs(float(r[kw])/6-float(r[kwh]))>1e-8:raise ValueError('Unit mismatch')
    inputs=dict(load_kwh=[float(r['load_kwh']) for r in rows],pv_forecast_kwh=[float(r['pv_forecast_kwh']) for r in rows],
        price_yuan_per_kwh=[float(r['price']) for r in rows],slot_ids=list(range(144)),initial_energy_kwh=6000,
        battery_params=BatteryParams(.9,.9,'bus'),input_metadata=dict(input_kind='standardized',data_version='sha256:'+digest,
        mapping_version='interval-end-v1',assumptions_version='eta0.9-each-bus-neutral6000-candidate-v1'))
    return inputs,source,digest


def main():
    inputs,source,digest=load_inputs()
    model,price,_=prepare_q1_inputs(**inputs)
    comparison=compare_q1_strategies(**inputs)
    if comparison['status']!='passed':raise RuntimeError('Real candidate comparison failed')
    # Attachment 1 has no actual date. Date is only an explicit representative-day anchor.
    start=datetime(2025,1,1,tzinfo=ZONE)
    contract=TableTimeContract(date(2025,1,1),tuple(start+timedelta(minutes=10*i) for i in range(145)),
                              inputs['input_metadata']['mapping_version'],'candidate')
    tables={name:extract_q1_tables(result,model=model,price_yuan_per_kwh=price,time_contract=contract,
             strategy=name,allow_candidate_time=True) for name,result in comparison['strategies'].items()}
    report={'input':inputs,'comparison':comparison,'tables':tables}
    output=ROOT/'analysis/real_q1_candidate'
    output.mkdir(parents=True,exist_ok=True)
    bundle={'scope':'real attachment 1; candidate physical interpretation and battery assumptions; not Gate 2 acceptance',
        'calendar_anchor_is_representative':True,'source':str(source.relative_to(ROOT)),'source_sha256':digest,'report':report,
        'code_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__).resolve(),ROOT/'scripts/run_q1_figures.py',*sorted((ROOT/'src').rglob('*.py'))]}}
    result_file=output/'result.json'
    result_file.write_text(json.dumps(bundle,default=encode,ensure_ascii=False,indent=2)+'\n')
    with (output/'summary.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(comparison['summary'][0]));writer.writeheader();writer.writerows(comparison['summary'])
    (output/'tables.md').write_text('# Q1真实附件候选表格\n\n附件1没有日期；2025-01-01仅为代表日锚点。候选假设未最终验收。\n\n'+
        '\n'.join(render_q1_tables_markdown(t) for t in tables.values()))
    saved=json.loads(result_file.read_text())
    paths=draw_case('attachment1_candidate',saved['report'],output,allow_candidate_time=True)
    if hashlib.sha256(source.read_bytes()).hexdigest()!=digest:raise RuntimeError('Source unexpectedly changed')
    (output/'figure_manifest.json').write_text(json.dumps({'source_sha256':hashlib.sha256(result_file.read_bytes()).hexdigest(),
        'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}},indent=2)+'\n')
    print(json.dumps(comparison['summary'],indent=2))


if __name__=='__main__':main()
