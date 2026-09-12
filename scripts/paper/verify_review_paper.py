"""Check the review paper's data bindings, January grid, and preserved tables."""
from pathlib import Path
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
import re
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads((ROOT/p).read_text())

def main(report_name="paper_validation.json"):
    checks=[]
    manifest=read('tmp/pdfs/classmate_review/figure_manifest.json')
    for name,digest in manifest['sources'].items():assert sha(ROOT/name)==digest,name
    for name,digest in manifest['figures'].items():assert sha(ROOT/'paper/figures'/name)==digest,name
    checks.append('All five new figures retain matching source and output hashes.')
    for directory,filename in [('q2_january_surface_v1','validation.json'),('q2_margin_oracle_v1','independent_validation.json'),('strict_q3_transfer_v1','independent_validation.json'),('strict_q4_transfer_v1','independent_validation.json')]:
        v=read(f'analysis/{directory}/{filename}')
        assert v['passed'] and v['result_sha256']==sha(ROOT/f'analysis/{directory}/result.json')
    checks.append('January, Q2, Q3 and Q4 results match their independent validations.')
    with (ROOT/'data/processed/team_delivery/day_base.csv').open() as f:
        price=np.array([float(r['price']) for r in csv.DictReader(f)])
    fees=defaultdict(float); counts=Counter()
    with gzip.open(ROOT/'analysis/q2_january_surface_v1/daily_traces.jsonl.gz','rt') as f:
        for line in f:
            r=json.loads(line); s=r['schedule']; key=(r['tau'],r['scale'])
            fees[key]+=np.asarray(s['G'])@price+5*np.asarray(s['U'])@price; counts[key]+=1
    assert len(fees)==81 and all(v==17 for v in counts.values())
    for r in read('analysis/q2_january_surface_v1/result.json')['scores']:
        assert abs(fees[r['tau'],r['scale']]-r['total_yuan'])<1e-5
    checks.append('81 surface nodes independently totalled from 1377 daily cost traces.')
    # Four dates, each emergency interval/value pair must survive the compact layout.
    pair=r'(\d{2}:\d{2}--\d{2}:\d{2})\s*&\s*(\d+\.\d+)'
    for q in ['q2','q3']:
        original=(ROOT/f'paper/latex/generated/{q}_selected.tex').read_text()
        revised=(ROOT/f'paper/latex/generated/{q}_review_selected.tex').read_text()
        assert Counter(re.findall(pair,original))==Counter(re.findall(pair,revised))
        assert re.findall(r'\\input\{([^}]+)\}',original)==re.findall(r'\\input\{([^}]+)\}',revised)
        for line in original.splitlines():
            if line.startswith('全天计划购电量'):assert line in revised
    checks.append('All eight specified-day summaries, table inputs and emergency entries preserved.')
    s=(ROOT/'paper/latex/main.tex').read_text()
    for forbidden in ['第五版','研究稿 V5','复现与交付索引','尚未重导','尚未按本轮','待独立验收','影响上限不到1']:
        assert forbidden not in s,forbidden
    log=(ROOT/'tmp/paper_build/main.log').read_text()
    for issue in ['Overfull','Missing character','undefined references','undefined citations']:
        assert issue not in log,issue
    checks.append('Current TeX log has no overflow, missing glyphs or unresolved references.')
    report={'passed':True,'checks':checks,'pdf_sha256':sha(ROOT/'paper/pdf/C_microgrid.pdf'),
            'scope':'Data and typesetting checks; page images inspected separately.'}
    dest=ROOT/'deliverables/review'/report_name
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--report-name', default='paper_validation.json')
    args = parser.parse_args()
    if Path(args.report_name).name != args.report_name:
        parser.error('--report-name must be a filename')
    main(args.report_name)
