"""Rebuild static paper figures/tables from frozen candidate artifacts; no optimization."""
from pathlib import Path
import csv, json, hashlib, shutil
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'deliverables/candidate_figures/v1'
TEX=ROOT/'deliverables/draft_v1/latex/generated'
OUT.mkdir(parents=True,exist_ok=True); TEX.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.grid':True,'grid.alpha':.16,'axes.axisbelow':True,'pdf.fonttype':42,'savefig.dpi':180})
blue='#235789'; gold='#D09B36'; orange='#BD643C'; grey='#74808B'
def read(p): return json.loads((ROOT/p).read_text())
def save(fig,name):
    fig.savefig(OUT/(name+'.pdf'),bbox_inches='tight'); fig.savefig(OUT/(name+'.png'),bbox_inches='tight'); plt.close(fig)
def table(name,headers,rows,align):
    text='\\begin{tabular}{'+align+'}\n\\toprule\n'+' & '.join(headers)+' \\\\\n\\midrule\n'
    text+='\n'.join(' & '.join(map(str,r))+' \\\\' for r in rows)+'\n\\bottomrule\n\\end{tabular}\n'
    (TEX/(name+'.tex')).write_text(text)
q1=read('analysis/real_q1_candidate/result.json')['report']
b=read('analysis/strict_q2_round2_v1/result.json')['strategies']; m=read('analysis/q2_margin_oracle_v1/result.json')['strategies']; q3=read('analysis/strict_q3_transfer_v1/result.json')['strategies']; voi=read('analysis/q3_voi_v1/result.json')['strategies']['adaptive']
q2={**b,**m}
# Q1: physical slot start versus SOC boundary, explicitly distinct lengths.
s=q1['comparison']['strategies']['optimized']['schedule']; h=np.arange(144)/6
fig,axes=plt.subplots(3,1,figsize=(8.2,6.7),sharex=True,layout='constrained')
axes[0].plot(h,np.array(q1['input']['load_kwh'])*6,color=blue,label='Load'); axes[0].plot(h,np.array(q1['input']['pv_forecast_kwh'])*6,color=gold,label='PV'); axes[0].set_ylabel('Power (kW)'); axes[0].legend(ncol=2,frameon=False)
axes[1].step(h,s['G'],where='post',color=grey,label='Grid'); axes[1].step(h,s['C'],where='post',color=blue,label='Charge'); axes[1].step(h,-np.array(s['D']),where='post',color=orange,label='Discharge (-)'); axes[1].set_ylabel('Energy (kWh/slot)'); axes[1].legend(ncol=3,frameon=False)
axes[2].plot(np.arange(145)/6,s['E'],color=blue); axes[2].axhline(1200,color=grey,ls='--'); axes[2].axhline(10800,color=grey,ls='--'); axes[2].set_ylabel('Stored energy (kWh)'); axes[2].set_xlabel('Physical time (h); right-end sampling candidate'); axes[2].set_xticks(range(0,25,4)); axes[2].set_xlim(0,24)
save(fig,'q1_dispatch')
# Q2 fee decomposition; oracle separately shaded, no misleading 3D.
keys=['B0','B1','B2','B3','fixedG_oracle','full_oracle']; labels=['B0','B1','B2','B3','Fixed-G\noracle','Full\noracle']; x=np.arange(6)
fig,ax=plt.subplots(figsize=(8.2,3.7),layout='constrained'); p=np.array([q2[k]['costs']['planned_yuan'] for k in keys])/1e6; u=np.array([q2[k]['costs']['emergency_yuan'] for k in keys])/1e6
ax.axvspan(3.5,5.5,color='#F0F1F2',zorder=0); ax.bar(x,p,color=blue,label='Planned'); ax.bar(x,u,bottom=p,color=orange,label='Emergency (5x price)'); ax.set_xticks(x,labels); ax.set_ylabel('Cost (million yuan)'); ax.set_ylim(0,19); ax.legend(ncol=2,frameon=False,loc='upper right')
for i,v in enumerate(p+u): ax.text(i,v+.2,f'{v:.3f}',ha='center',fontsize=9)
save(fig,'q2_costs')
months=sorted(q2['B2']['monthly_total_yuan']); savings=np.array([q2['B0']['monthly_total_yuan'][d]-q2['B2']['monthly_total_yuan'][d] for d in months])/1e4
fig,ax=plt.subplots(figsize=(8.2,3.1),layout='constrained'); ax.bar(range(11),savings,color=blue); ax.set_xticks(range(11),[str(int(d[-2:])) for d in months]); ax.set_xlabel('Month (2025)'); ax.set_ylabel('B0 minus B2 (10,000 yuan)'); save(fig,'q2_monthly_savings')
# Four prescribed days, shared scales, battery and emergency energy separate axes/panels.
dates=['2025-03-20','2025-06-21','2025-09-23','2025-12-21']; traces={}
with (ROOT/'analysis/q2_margin_oracle_v1/B2.jsonl').open() as f:
    for line in f:
        r=json.loads(line)
        if r['day'] in dates: traces[r['day']]=r
fig,axes=plt.subplots(2,4,figsize=(10.2,4.6),sharex=True,sharey='row',layout='constrained')
for j,d in enumerate(dates):
    z=traces[d]['schedule']; axes[0,j].plot(np.arange(145)/6,np.array(z['E'])/1000,color=blue); axes[0,j].set_title(d,fontsize=10); axes[0,j].set_ylim(0,12); axes[1,j].bar(h,z['U'],width=1/6,color=orange); axes[1,j].set_xticks([0,12,24]); axes[1,j].set_xlabel('Hour'); axes[1,j].set_xlim(0,24)
axes[0,0].set_ylabel('Stored energy (MWh)'); axes[1,0].set_ylabel('Emergency (kWh/slot)'); save(fig,'q2_selected_days')
keys3=['base_zero','base_fresh','margin_zero','margin_fresh','adaptive']; data3={**q3,'adaptive':voi}; labels3=['Baseline\nfixed','Baseline\nupdates','Margin\nfixed','Margin\nupdates','Margin\ngated']
fig,ax=plt.subplots(figsize=(8.2,3.8),layout='constrained'); bot=np.zeros(5)
for field,col,label in [('planned_yuan',blue,'Planned'),('adjustment_yuan',gold,'Adjustment'),('emergency_yuan',orange,'Emergency')]:
    vals=np.array([data3[k]['costs'][field] for k in keys3])/1e6; ax.bar(range(5),vals,bottom=bot,color=col,label=label); bot+=vals
ax.set_xticks(range(5),labels3); ax.set_ylabel('Cost (million yuan)'); ax.set_ylim(0,19); ax.legend(ncol=3,frameon=False,loc='upper right')
for i,v in enumerate(bot): ax.text(i,v+.2,f'{v:.3f}',ha='center',fontsize=9)
save(fig,'q3_costs')
vals=np.array([q3['margin_zero']['monthly_total_yuan'][d]-voi['monthly_total_yuan'][d] for d in months])/1000
fig,ax=plt.subplots(figsize=(8.2,3.1),layout='constrained'); ax.bar(range(11),vals,color=[blue if v>=0 else gold for v in vals]); ax.axhline(0,color='black',lw=.7); ax.set_xticks(range(11),[str(int(d[-2:])) for d in months]); ax.set_xlabel('Month (2025)'); ax.set_ylabel('Fixed minus gated (1,000 yuan)'); save(fig,'q3_gate_monthly')
# Machine-generated numeric tables; yuan kept to cents.
table('q2_costs',['方案','计划费/元','紧急费/元','总费/元'],[[k.replace('_',r'\_')]+[f"{q2[k]['costs'][f]:,.2f}" for f in ['planned_yuan','emergency_yuan','total_yuan']] for k in keys],'lrrr')
table('q3_costs',['方案','计划费/万元','调整费/万元','紧急费/万元','总费/万元'],[[label]+[f"{data3[k]['costs'][f]/1e4:.4f}" for f in ['planned_yuan','adjustment_yuan','emergency_yuan','total_yuan']] for k,label in zip(keys3,['基线固定','基线更新','裕量固定','裕量更新','裕量门控'])],'lrrrr')
table('q1_purchase',['物理时段','购电量/kWh'],[[f'{hour:02}:00--{hour:02}:10',f"{s['G'][hour*6]:.3f}"] for hour in [10,12,14,16,18,20]],'lr')
table('q1_battery',['物理时段','充电量/kWh','放电量/kWh'],[[f'{i*4:02}:00--{(i+1)*4:02}:00',f"{sum(s['C'][i*24:(i+1)*24]):.3f}",f"{sum(s['D'][i*24:(i+1)*24]):.3f}"] for i in range(6)],'lrr')
# Detailed prescribed-day tables and merged emergency intervals for both selected policies.
rows_csv=[]
for tag,path in [('q2','analysis/q2_margin_oracle_v1/B2.jsonl'),('q3','analysis/strict_q3_transfer_v1/margin_zero.jsonl')]:
    selected={}
    for line in (ROOT/path).open():
        row=json.loads(line)
        if row['day'] in dates: selected[row['day']]=row
    chunks=[]
    for d in dates:
        row=selected[d]; z=row['schedule']; chunks.append(r'\subsubsection*{'+d+'}')
        table(tag+'_'+d+'_p',['时段','购电量/kWh'],[[f'{hh:02}:00--{hh:02}:10',f"{z['G'][hh*6]:.3f}"] for hh in [10,12,14,16,18,20]],'lr')
        table(tag+'_'+d+'_b',['时段','充电量/kWh','放电量/kWh'],[[f'{i*4:02}:00--{(i+1)*4:02}:00',f"{sum(z['C'][i*24:(i+1)*24]):.3f}",f"{sum(z['D'][i*24:(i+1)*24]):.3f}"] for i in range(6)],'lrr')
        chunks += [r'\begin{center}\small\input{generated/'+tag+'_'+d+'_p.tex}'+r'\quad\input{generated/'+tag+'_'+d+'_b.tex}'+r'\end{center}',f"全天计划购电量 {sum(z['G']):.3f} kWh，总费用 {row['costs']['total_yuan']:,.2f} 元，其中紧急费 {row['costs']['emergency_yuan']:,.2f} 元；日初、日末储电量均为6000 kWh。"]
        intervals=[]; start=None
        for i in range(145):
            active=i<144 and z['U'][i]>1e-6
            if active and start is None: start=i
            if not active and start is not None:
                label=f'{start//6:02}:{start%6*10:02}--{i//6:02}:{i%6*10:02}'; val=sum(z['U'][start:i]); intervals.append((label,val)); rows_csv.append([tag,d,label,val]); start=None
        chunks.append(r'\begin{longtable}{lr}\toprule 紧急购电物理时段 & 电量/kWh\\\midrule\endhead')
        chunks.extend(f'{label} & {val:.3f} '+r'\\' for label,val in intervals)
        chunks.append(r'\bottomrule\end{longtable}')
    (TEX/(tag+'_selected.tex')).write_text('\n'.join(chunks))
with (OUT/'selected_emergency_intervals.csv').open('w') as f:
    w=csv.writer(f); w.writerow(['question','date','physical_interval_candidate','emergency_kwh']); w.writerows(rows_csv)
manifest={'status':'candidate_not_final','period':'2025-02-01 through 2025-12-31; Q1 representative day','time_policy':'right-end sampling; physical slots 00:00 to 24:00; Excel mapping unresolved','figures':[]}
for p in sorted(OUT.glob('*.pdf')): manifest['figures'].append({'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
manifest['sources']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['analysis/real_q1_candidate/result.json','analysis/strict_q2_round2_v1/result.json','analysis/q2_margin_oracle_v1/result.json','analysis/strict_q3_transfer_v1/result.json','analysis/q3_voi_v1/result.json','analysis/q2_margin_oracle_v1/B2.jsonl','analysis/strict_q3_transfer_v1/margin_zero.jsonl']}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
print('Built',len(manifest['figures']),'figures and selected-day tables')
