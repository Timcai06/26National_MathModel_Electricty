"""January-only parameter response surface, with all grid nodes actually replayed."""
from pathlib import Path
import sys,os,json,csv,hashlib,time,gzip
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R));os.environ.setdefault('MPLCONFIGDIR',str(R/'tmp/matplotlib'))
import numpy as np
from scripts.run_q2_margin_oracle import corrected,make_plan,MarginConfig,execute
from scripts.run_real_q2_forecast import load_rows,parse_days
from scripts.run_real_q23 import audited_csv
A=R/'analysis/q2_january_surface_v1';O=R/'deliverables/candidate_figures/v3_3d';A.mkdir(exist_ok=True);O.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
taus=np.round(np.linspace(.5,.9,9),3);scales=np.round(np.linspace(.25,1.25,9),3)
protocol={'scope':'Posthoc January development-only sensitivity; no new Feb-Dec tuning or evaluation; original selected parameters unchanged','tau_grid':taus.tolist(),'scale_grid':scales.tolist(),'scoring_dates':['2025-01-15','2025-01-31'],'history':'January only; each forecast sees only prior completed days','controller':'B0 strict','terminal_kwh':6000,'original_parameter':[.8,1.0],'interpolation':'Piecewise planar faces between measured grid nodes for display only; no smoothed optimized surface','code_sha256':sha(Path(__file__))}
if not (A/'result.json').exists():
 (A/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2))
 rows,source,digest=load_rows();days=parse_days(rows,delay_minutes=0)[:31]
 assert len(days)==31
 pr,pdigest=audited_csv('data/processed/team_delivery/day_base.csv');price=np.array([float(r['price']) for r in pr]);scores=[];before=time.monotonic()
 with gzip.open(A/'daily_traces.jsonl.gz','wt') as f:
  for j,k in enumerate(scales):
   for i,tau in enumerate(taus):
    conf=MarginConfig(tau=float(tau),scale=float(k));cost={'planned_yuan':0.,'emergency_yuan':0.,'total_yuan':0.};state=6000.
    for idx in range(14,31):
     prediction,sources,audit=corrected(days,idx,conf);g=make_plan(prediction,price);r=execute(days[idx],price,prediction,sources,g,state,'B0');state=r['terminal_energy_kwh'];assert r['diagnostics']['passed'];r.update(tau=float(tau),scale=float(k),margin=audit);f.write(json.dumps(r)+'\n')
     for field in cost:cost[field]+=r['costs'][field]
    scores.append({'tau':float(tau),'scale':float(k),**cost})
   print(f'{j+1}/9 grid rows, {(j+1)*9*17} day replays, {time.monotonic()-before:.1f}s',flush=True)
 report={'protocol':protocol,'scores':scores,'days_replayed':81*17,'runtime_seconds':time.monotonic()-before,'input_sha256':{str(source.relative_to(R)):digest,'data/processed/team_delivery/day_base.csv':pdigest},'daily_trace_sha256':sha(A/'daily_traces.jsonl.gz')};(A/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
else:report=json.loads((A/'result.json').read_text())
# Independent per-trace physical and cost arithmetic, and exact old-grid intersection.
rows,source,digest=load_rows();jan=parse_days(rows,delay_minutes=0)[:31];byday={str(d.day):d for d in jan}
pr,_=audited_csv('data/processed/team_delivery/day_base.csv');price=np.array([float(r['price']) for r in pr]);tot={};maxres=0.;n=0
with gzip.open(A/'daily_traces.jsonl.gz','rt') as f:
 for line in f:
  r=json.loads(line);s={k:np.array(v) for k,v in r['schedule'].items()};day=byday[r['day']];bal=s['G']+day.pv_kwh+s['D']+s['U']-day.load_kwh-s['C']-s['W'];state=s['E'][1:]-s['E'][:-1]-.9*s['C']+s['D']/.9;maxres=max(maxres,float(abs(bal).max()),float(abs(state).max()));assert maxres<1e-6;assert min(s['E'])>=1200-1e-6 and max(s['E'])<=10800+1e-6;assert max(s['C'])<=5000/6+1e-6 and max(s['D'])<=5000/6+1e-6;assert np.max(np.minimum(s['C'],s['D']))<1e-6;assert abs(s['E'][0]-6000)<1e-6 and abs(s['E'][-1]-6000)<1e-6
  fee=float(s['G']@price+s['U']@(5*price));assert abs(fee-r['costs']['total_yuan'])<1e-5;key=(r['tau'],r['scale']);tot[key]=tot.get(key,0)+fee;n+=1
for r in report['scores']:assert abs(tot[r['tau'],r['scale']]-r['total_yuan'])<1e-5
old=json.loads((R/'analysis/q2_margin_oracle_v1/frozen_selection.json').read_text());errors=[]
for r in old['scores'][1:]:
 key=(r['config']['tau'],r['config']['scale']);err=abs(tot[key]-r['january_total_yuan']);assert err<1e-5;errors.append(err)
validation={'passed':True,'day_replays_verified':n,'max_physical_residual_kwh':maxres,'old_grid_intersection_checks':len(errors),'max_old_grid_cost_difference_yuan':max(errors),'original_parameter_unchanged':True,'result_sha256':sha(A/'result.json')};(A/'validation.json').write_text(json.dumps(validation,indent=2))
# Figure: 3D actual response mesh + aligned 2D contour; selected old parameter distinguished from new grid minimum.
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.colors import Normalize
fm.fontManager.addfont('/System/Library/Fonts/Supplemental/Arial Unicode.ttf');plt.rcParams.update({'font.family':['Arial Unicode MS','DejaVu Sans'],'font.size':10,'axes.unicode_minus':False,'pdf.fonttype':42})
X,Y=np.meshgrid(taus,scales);Z=np.array([[tot[float(t),float(k)]/1e4 for t in taus] for k in scales]);vmin,vmax=float(Z.min()),float(Z.max());norm=Normalize(vmin,vmax);cmap=plt.get_cmap('YlGnBu_r');ix,iy=np.argwhere(Z==Z.min())[0];fixed=float(tot[.8,1.]/1e4);floor=vmin-2
fig=plt.figure(figsize=(11.8,5.3));gs=fig.add_gridspec(1,2,width_ratios=[1.12,1],left=.03,right=.91,bottom=.14,top=.87,wspace=.28)
a=fig.add_subplot(gs[0],projection='3d',computed_zorder=False);b=fig.add_subplot(gs[1]);a.set_proj_type('ortho');a.view_init(elev=26,azim=50)
a.plot_surface(X,Y,Z,cmap=cmap,norm=norm,rstride=1,cstride=1,edgecolor='#EDF2F4',linewidth=.5,alpha=.95,antialiased=True,zorder=1);a.contour(X,Y,Z,zdir='z',offset=floor,levels=8,cmap=cmap,norm=norm,linewidths=.65);a.scatter(X,Y,np.full_like(Z,floor),s=5,c='#7D8790',alpha=.5)
a.scatter([.8],[1.],[fixed],marker='*',s=135,c='#D5A535',edgecolors='black',linewidth=.7,depthshade=False,zorder=10);a.plot([.8,.8],[1,1],[floor,fixed],color='#5B6470',ls='--',lw=.8)
a.scatter([taus[iy]],[scales[ix]],[vmin],marker='o',s=45,facecolors='none',edgecolors='#B15355',depthshade=False,zorder=11)
a.set(xlabel='分位数水平 τ',ylabel='裕量系数 κ',zlabel='1月开发期总费 / 万元',zlim=(floor,vmax+.5));a.set_xticks([.5,.6,.7,.8,.9]);a.set_yticks([.25,.5,.75,1,1.25]);a.tick_params(labelsize=8,pad=1);a.set_box_aspect((1,1,.75));a.set_title('a  真实参数网格的费用响应面',loc='left',pad=18)
for axis in [a.xaxis,a.yaxis,a.zaxis]:axis.pane.fill=False;axis._axinfo['grid']['color']=(.84,.87,.9,.6)
im=b.contourf(X,Y,Z,levels=np.linspace(vmin,vmax,13),cmap=cmap,norm=norm);cs=b.contour(X,Y,Z,levels=np.linspace(vmin,vmax,7),colors='#6E8793',linewidths=.65);b.clabel(cs,inline=True,fontsize=8,fmt='%.1f');b.scatter(X,Y,s=9,c='#637783',alpha=.6)
b.scatter([.8],[1],s=150,marker='*',c='#D5A535',edgecolors='black',linewidth=.7,zorder=6,label='原方案固定参数');b.scatter([taus[iy]],[scales[ix]],s=85,facecolors='none',edgecolors='#B15355',linewidths=1.4,zorder=7,clip_on=False,label='本次开发网格最低点');b.annotate(f'原方案 (0.80, 1.00)\n{fixed:.3f} 万元',xy=(.8,1),xytext=(.52,1.1),arrowprops={'arrowstyle':'-','color':'#5B6470'},fontsize=9,bbox={'facecolor':'white','edgecolor':'none','alpha':.85})
b.set(xlabel='分位数水平 τ',ylabel='裕量系数 κ',xlim=(.5,.9),ylim=(.25,1.25));b.set_xticks([.5,.6,.7,.8,.9]);b.set_title('b  同一数据的等高线与实测节点',loc='left',pad=18);b.legend(loc='lower left',fontsize=8,framealpha=.85)
cax=fig.add_axes([.935,.18,.016,.61]);fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),cax=cax,label='总费用 / 万元')
fig.text(.06,.025,'81个参数组合 × 17个开发日；网格间仅作分片连接。原参数不变，未对2—12月重新选型。',fontsize=10,color='#576571')
for ext in ['pdf','png']:fig.savefig(O/f'q2_cost_response_3d.{ext}',dpi=200,bbox_inches='tight')
plt.close(fig)
with (O/'response_grid.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(report['scores'][0]));w.writeheader();w.writerows(report['scores'])
meta={'status':'candidate_development_sensitivity_not_new_main_model','source_result_sha256':sha(A/'result.json'),'validation_sha256':sha(A/'validation.json'),'original_point':{'tau':.8,'scale':1.,'january_total_yuan':fixed*1e4},'grid_minimum':{'tau':float(taus[iy]),'scale':float(scales[ix]),'january_total_yuan':vmin*1e4},'plot_method':'matplotlib plot_surface and contourf; orthographic view; actual 9x9 grid; no Blender','visual_review':'Both final atlas pages rendered with Poppler and inspected; no clipping or font warnings observed; human acceptance pending.','files':{p.name:sha(p) for p in O.glob('*') if p.is_file() and p.suffix in ['.pdf','.png','.csv']}}
(O/'manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2));print(json.dumps(meta,ensure_ascii=False,indent=2))
