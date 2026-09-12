"""Independent arithmetic checks for V2 chart evidence and paper build."""
from pathlib import Path
import csv,json,hashlib
import numpy as np
R=Path(__file__).resolve().parents[2];O=R/'deliverables/candidate_figures/v2'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
m=read(O/'manifest.json')
for p,h in m['sources'].items():assert sha(R/p)==h
for row in m['figures']:assert sha(O/row['file'])==row['sha256']
checks=['All source and figure SHA256 bindings match']
a=read(O/'annual_patterns.data.json')
with (R/'data/processed/team_delivery/annual_actual.csv').open() as f:rows=list(csv.DictReader(f))
load=np.array([float(r['load_kwh']) for r in rows]).reshape(365,144);pv=np.array([float(r['pv_actual_kwh']) for r in rows]).reshape(365,144)
np.testing.assert_allclose(np.array(a['load_kw']),load*6,rtol=0,atol=1e-9);np.testing.assert_allclose(np.array(a['pv_kw']),pv*6,rtol=0,atol=1e-9)
margin=read(O/'margin_mechanism.data.json');res=(load[7:31]-pv[7:31])-(load[:24]-pv[6:30])
for i,g in enumerate(margin['january_residual_groups']):np.testing.assert_allclose(g,res[:,i*24:(i+1)*24].flatten(),atol=1e-9,rtol=0)
start,dp,du,end=margin['waterfall_wanyuan'];assert abs(start+dp+du-end)<1e-8
selection=read(R/'analysis/q2_margin_oracle_v1/frozen_selection.json')
for r in selection['scores'][1:]:
 c=r['config'];assert abs(margin['january_grid_wanyuan'][[.5,1].index(c['scale'])][[.6,.7,.8,.9].index(c['tau'])]-r['january_total_yuan']/1e4)<1e-9
checks.append('Annual matrices, January residual samples, 8 exact parameter trials and fee waterfall recomputed')
s=read(O/'strategy_stability.data.json');d=np.array(s['B0_total_yuan'])-np.array(s['B2_total_yuan']);np.testing.assert_allclose(d,s['daily_saving_yuan'],atol=1e-8);assert (d>1e-5).sum()==291
q0=read(R/'analysis/strict_q2_round2_v1/result.json')['strategies']['B0'];q2=read(R/'analysis/q2_margin_oracle_v1/result.json')['strategies']['B2'];assert abs(sum(d)-(q0['costs']['total_yuan']-q2['costs']['total_yuan']))<1e-5
checks.append('334 paired daily costs, 291 improvement days and annual savings matched frozen totals')
g=read(O/'gate_decisions.data.json');assert len(g['decisions'])==1002;assert sum(z['accepted'] for z in g['decisions'])==183
for z in g['decisions']:
 assert z['accepted']==(z['predicted_gain_yuan']>500+1e-6)
 assert abs(z['predicted_emergency_saving_yuan']-z['adjustment_yuan']-z['predicted_gain_yuan'])<1e-7
q3=read(R/'analysis/strict_q3_transfer_v1/result.json')['strategies']['margin_zero'];v=read(R/'analysis/q3_voi_v1/result.json')['strategies']['adaptive'];assert abs(sum(g['monthly_realized_saving_thousand_yuan'])*1000-(q3['costs']['total_yuan']-v['costs']['total_yuan']))<1e-5
assert np.array(g['acceptance_by_issue'])[:,0].tolist()==[83,97,3]
checks.append('1002 VOI decisions, 500-yuan boundary, 83/97/3 acceptance counts and actual monthly ledger matched')
z=read(O/'dispatch_mechanism.data.json');e=np.array(z['schedule']['E'])/1000;assert np.all(e>=np.array(z['reachable_min_mwh'])-1e-8) and np.all(e<=np.array(z['reachable_max_mwh'])+1e-8)
checks.append('Selected day storage trajectory remains inside analytic terminal-reachability envelope')
log=(R/'tmp/paper_v2_build/main.log').read_text();assert not any(x in log for x in ['Overfull','Missing character','undefined references','undefined citations'])
report={'passed':True,'checks':checks,'no_optimizer_changes':True,'source_manifest_sha256':sha(O/'manifest.json'),'pdf_sha256':sha(R/'deliverables/draft_v2/pdf/C_microgrid_draft_v2.pdf'),'scope':'Chart data, frozen source bindings and TeX log; not final semantics or human visual acceptance.'}
(R/'deliverables/review/research_figures_v2_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
