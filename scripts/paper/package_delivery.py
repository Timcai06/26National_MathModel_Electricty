"""Curate the V1 handoff without moving hash-bound experiment evidence."""
from pathlib import Path
import hashlib,json,shutil,zipfile
R=Path(__file__).resolve().parents[2]; D=R/'deliverables'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
old=[]
for p in sorted((R/'outputs').glob('*/result*_candidate.xlsx')):
    if 'synthetic' in p.name: continue
    dst=D/'legacy_excel'/p.name; shutil.copy2(p,dst)
    old.append({'file':str(dst.relative_to(D)),'source':str(p.relative_to(R)),'sha256':sha(dst),'status':'legacy_candidate_not_aligned_with_draft_v1'})
(D/'legacy_excel/manifest.json').write_text(json.dumps(old,ensure_ascii=False,indent=2))
shutil.copy2(R/'tmp/paper_v1_build/main.pdf',D/'draft_v1/pdf/C_microgrid_draft_v1.pdf')
for name in ['strict_q2_round2_v1','q2_margin_oracle_v1','strict_q3_transfer_v1','q3_voi_v1']:
    dst=D/'review'/name; dst.mkdir(exist_ok=True)
    for filename in ['result.json','independent_validation.json','comparison.csv','monthly_comparison.csv','frozen_selection.json']:
        p=R/'analysis'/name/filename
        if p.exists(): shutil.copy2(p,dst/filename)
# Delete only explicitly regenerable local cache files; record paths and bytes.
removed=[]
for base in ['src','scripts','tests']:
    for p in list((R/base).rglob('__pycache__')):
        if p.is_dir():
            removed.append({'path':str(p.relative_to(R)),'bytes':sum(f.stat().st_size for f in p.rglob('*') if f.is_file())}); shutil.rmtree(p)
p=R/'.pytest_cache'
if p.exists(): removed.append({'path':'.pytest_cache','bytes':sum(f.stat().st_size for f in p.rglob('*') if f.is_file())});shutil.rmtree(p)
p=R/'.DS_Store'
if p.exists(): removed.append({'path':'.DS_Store','bytes':p.stat().st_size});p.unlink()
report={'removed_regenerable_caches':removed,'preserved':'raw inputs, standardized data, model code, tests, hash-bound analysis, old export evidence and environment','old_excel_copied_not_recomputed':old}
(D/'review/organization_log.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('Curated',len(old),'legacy workbooks; cleaned',len(removed),'cache entries')
