"""Verify source bindings, generated numerical tables and handoff copies."""
from pathlib import Path
import json,hashlib,csv,subprocess
R=Path(__file__).resolve().parents[2];D=R/'deliverables';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
checks=[]
for name in ['strict_q2_round2_v1','q2_margin_oracle_v1','strict_q3_transfer_v1','q3_voi_v1']:
 p=R/'analysis'/name;v=json.loads((p/'independent_validation.json').read_text());assert v['passed'];assert v['result_sha256']==sha(p/'result.json');checks.append(name+': independent validation bound to current result')
f=json.loads((D/'candidate_figures/v1/manifest.json').read_text())
for p,h in f['sources'].items(): assert sha(R/p)==h
for row in f['figures']: assert sha(D/'candidate_figures/v1'/row['file'])==row['sha256']
for row in json.loads((D/'legacy_excel/manifest.json').read_text()): assert sha(D/row['file'])==sha(R/row['source'])==row['sha256']
for label,p in [('q2','q2_margin_oracle_v1/B2.jsonl'),('q3','strict_q3_transfer_v1/margin_zero.jsonl')]:
 selected={}
 for line in (R/'analysis'/p).open():
  row=json.loads(line)
  if row['day'] in ['2025-03-20','2025-06-21','2025-09-23','2025-12-21']:selected[row['day']]=row
 for day,row in selected.items():
  tex=(D/f'draft_v1/latex/generated/{label}_{day}_p.tex').read_text()
  for h in [10,12,14,16,18,20]: assert f"{row['schedule']['G'][h*6]:.3f}" in tex
  with (D/'candidate_figures/v1/selected_emergency_intervals.csv').open() as c: vals=[float(z['emergency_kwh']) for z in csv.DictReader(c) if z['question']==label and z['date']==day]
  assert abs(sum(vals)-sum(row['schedule']['U']))<1e-4
checks.append('8 prescribed-day purchase tables and merged emergency totals matched trajectories')
log=(R/'tmp/paper_v1_build/main.log').read_text(); assert not any(x in log for x in ['Overfull','Missing character','undefined references','undefined citations'])
info=subprocess.check_output(['rtk','proxy','pdfinfo',str(D/'draft_v1/pdf/C_microgrid_draft_v1.pdf')],text=True)
checks.append('XeLaTeX log: no overfull boxes, missing characters or undefined citations/references')
report={'passed':True,'checks':checks,'pdf_sha256':sha(D/'draft_v1/pdf/C_microgrid_draft_v1.pdf'),'pdf_info':info,'visual_review':'All 18 pages reviewed as contact sheets; page 4 inspected enlarged; no clipping or collisions observed at reviewed resolutions. Final human acceptance pending.','not_validated':'Official time mapping; Q4 strict migration; new Excel exports; competition format final compliance; full external literature review.'}
(D/'review/draft_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'passed':True,'checks':len(checks),'pdf_sha256':report['pdf_sha256']},indent=2))
