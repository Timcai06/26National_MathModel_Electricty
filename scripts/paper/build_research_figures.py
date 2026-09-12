"""V2 research plates: frozen evidence only, no optimization or parameter selection."""
from pathlib import Path
import os,json,csv,hashlib
R=Path(__file__).resolve().parents[2]
os.environ.setdefault('MPLCONFIGDIR',str(R/'tmp/matplotlib'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.colors import TwoSlopeNorm
from matplotlib.backends.backend_pdf import PdfPages
from scipy.stats import gaussian_kde
O=R/'deliverables/candidate_figures/v2';O.mkdir(parents=True,exist_ok=True)
fm.fontManager.addfont('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
plt.rcParams.update({'font.family':['Arial Unicode MS','DejaVu Sans'],'font.size':10,'axes.titlesize':11,'axes.labelsize':10,'xtick.labelsize':9,'ytick.labelsize':9,'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.65,'axes.axisbelow':True,'grid.color':'#DCE0E5','grid.linewidth':.5,'grid.alpha':.6,'pdf.fonttype':42,'axes.unicode_minus':False})
BLUE='#285F8A';TEAL='#318D94';GOLD='#D3A447';RED='#B95F59';GREY='#7C8490'
sources={}; metadata=[]; tables={}; atlas=PdfPages(O/'research_figures_v2.pdf')
def source(p):
 p=R/p;sources[str(p.relative_to(R))]=hashlib.sha256(p.read_bytes()).hexdigest();return p

def js(p):return json.loads(source(p).read_text())
def traces(p):
 with source(p).open() as f:return [json.loads(x) for x in f]
def panel(ax,letter,title,x=None,y=None):
 ax.set_title(f'{letter}  {title}',loc='left',pad=11)
 if x:ax.set_xlabel(x)
 if y:ax.set_ylabel(y)
 ax.grid(True,axis='y')
def fig4():return plt.subplots(2,2,figsize=(10.8,7.5),layout='constrained')
def save(fig,name,title,notes,data):
 fig.get_layout_engine().set(h_pad=.11,w_pad=.14,hspace=.13,wspace=.07)
 fig.savefig(O/(name+'.pdf'),bbox_inches='tight');fig.savefig(O/(name+'.png'),dpi=190,bbox_inches='tight');atlas.savefig(fig,bbox_inches='tight');plt.close(fig)
 tables[name]=data;metadata.append({'id':name,'title':title,'notes':notes,'file':name+'.pdf'})
with source('data/processed/team_delivery/annual_actual.csv').open() as f:rows=list(csv.DictReader(f))
assert len(rows)==365*144
L=np.array([float(x['load_kwh']) for x in rows]).reshape(365,144)
V=np.array([float(x['pv_actual_kwh']) for x in rows]).reshape(365,144)
dates=np.array([rows[d*144]['date'] for d in range(365)]);hours=(np.arange(144)+.5)/6
b0r=traces('analysis/strict_q2_round2_v1/B0.jsonl');b0r=[r for r in b0r if r['day']>='2025-02-01']
b2r=traces('analysis/q2_margin_oracle_v1/B2.jsonl');ar=traces('analysis/q3_voi_v1/adaptive.jsonl')
assert len(b0r)==len(b2r)==len(ar)==334
assert [r['day'] for r in b0r]==[r['day'] for r in b2r]==[r['day'] for r in ar]
b0=js('analysis/strict_q2_round2_v1/result.json')['strategies']['B0'];b2=js('analysis/q2_margin_oracle_v1/result.json')['strategies']['B2'];q3=js('analysis/strict_q3_transfer_v1/result.json')['strategies'];voi=js('analysis/q3_voi_v1/result.json')['strategies']['adaptive'];selection=js('analysis/q2_margin_oracle_v1/frozen_selection.json')
for p in ['strict_q2_round2_v1','q2_margin_oracle_v1','strict_q3_transfer_v1','q3_voi_v1']:
 v=js(f'analysis/{p}/independent_validation.json');assert v['passed'] and v['result_sha256']==sources[f'analysis/{p}/result.json']
# 1. Temporal geometry: actual measured grid, no interpolation between observations.
fig,axs=fig4();mt=[i for i,d in enumerate(dates) if d.endswith('-01')]
for ax,arr,letter,title,cmap,lims in [(axs[0,0],L*6/1000,'a','全年负荷：日期 × 时刻','YlGnBu',(0,float(L.max()*6/1000))),(axs[0,1],V*6/1000,'b','全年光伏：日期 × 时刻','YlOrBr',(0,float(V.max()*6/1000))),(axs[1,0],(L-V)*6/1000,'c','净负荷：正值为缺口，负值为富余','RdBu_r',None)]:
 args={'vmin':lims[0],'vmax':lims[1]} if lims else {'norm':TwoSlopeNorm(vmin=float(((L-V)*6/1000).min()),vcenter=0,vmax=float(((L-V)*6/1000).max()))}
 im=ax.imshow(arr,aspect='auto',origin='upper',extent=(0,24,365,0),cmap=cmap,interpolation='nearest',**args);ax.set_yticks(np.array(mt)+.5,[str(int(dates[i][5:7]))+'月' for i in mt]);ax.set_xticks(range(0,25,6));panel(ax,letter,title,'物理时刻 / h');ax.grid(False);fig.colorbar(im,ax=ax,pad=.02,shrink=.87,label='功率 / MW')
ax=axs[1,1]
for inds,label,c,ls in [(np.r_[0:59,334:365],'冬季',BLUE,'-'),(np.arange(59,151),'春季',TEAL,'--'),(np.arange(151,243),'夏季',RED,'-.'),(np.arange(243,334),'秋季',GOLD,':')]:
 arr=(L-V)[inds]*6/1000;med=np.median(arr,axis=0);lo,hi=np.quantile(arr,[.1,.9],axis=0);ax.plot(hours,med,label=label,color=c,ls=ls,lw=1.4);ax.fill_between(hours,lo,hi,color=c,alpha=.08)
ax.axhline(0,color=GREY,lw=.7);ax.set_xticks(range(0,25,6));ax.set_xlim(0,24);ax.legend(ncol=2,frameon=False,fontsize=9);panel(ax,'d','季节日内净负荷轮廓','物理时刻 / h','功率 / MW')
save(fig,'annual_patterns','全年负荷、光伏及净负荷结构','2025全年实际值；阴影为季节内逐槽10%至90%经验分位范围，不是置信区间。',{'dates':dates.tolist(),'load_kw':(L*6).tolist(),'pv_kw':(V*6).tolist()})
# 2. Evidence chain for safety margin: residual -> actual parameter grid -> rolling correction -> fee bridge.
fig,axs=fig4();res=(L[7:31]-V[7:31])-(L[:24]-V[6:30]);groups=[res[:,i*24:(i+1)*24].flatten() for i in range(6)]
ax=axs[0,0];grid=np.linspace(min(x.min() for x in groups),max(x.max() for x in groups),450);q80=[]
for i,x in enumerate(groups):
 density=gaussian_kde(x)(grid);density=density/density.max()*.75;ax.fill_between(grid,i,i+density,color=plt.cm.YlGnBu(.32+i*.105),alpha=.82);ax.plot(grid,i+density,color='white',lw=.5);q=float(np.quantile(x,.8));q80.append(q);ax.plot([q,q],[i,i+.72],color=RED,lw=1.25);ax.text(grid.max(),i+.1,f'n={len(x)}',ha='right',fontsize=8,color=GREY)
ax.axvline(0,color=GREY,ls=':',lw=.8);ax.set_yticks(range(6),[f'{i*4:02}—{(i+1)*4:02}时' for i in range(6)]);panel(ax,'a','一月分时残差分布（红线：80%分位）','实际净负荷 − 基础预测 / kWh');ax.grid(False)
ax=axs[0,1];mat=np.empty((2,4))
for r in selection['scores'][1:]:mat[[.5,1].index(r['config']['scale']),[.6,.7,.8,.9].index(r['config']['tau'])]=r['january_total_yuan']/1e4
im=ax.imshow(mat,cmap='YlGnBu_r',aspect='auto',interpolation='nearest');ax.set_xticks(range(4),['0.6','0.7','0.8','0.9']);ax.set_yticks(range(2),['0.5','1.0']);
for i in range(2):
 for j in range(4):ax.text(j,i,f'{mat[i,j]:.2f}',ha='center',va='center',color='white' if mat[i,j]<94.5 else '#233240')
ax.plot(2,1,marker='s',ms=47,mfc='none',mec=RED,mew=2);panel(ax,'b','已运行参数组合：开发期总费用 / 万元','分位数水平 τ','裕量系数 κ');ax.grid(False);ax.text(.01,-.26,'1月15—31日；零裕量参考：97.10万元',transform=ax.transAxes,fontsize=9,color=GREY)
ax=axs[1,0];corr=np.array([r['margin']['correction_kwh'][::24] for r in b2r]);im=ax.imshow(corr.T,aspect='auto',origin='lower',cmap='YlGnBu',extent=(0,334,0,6),interpolation='nearest');tick=[i for i,r in enumerate(b2r) if r['day'].endswith('-01')];ax.set_xticks(tick,[str(int(b2r[i]['day'][5:7])) for i in tick]);ax.set_yticks(np.arange(6)+.5,[f'{i*4:02}—{(i+1)*4:02}' for i in range(6)]);panel(ax,'c','执行时实际使用的历史残差裕量','月份（2025年）','四小时时段');ax.grid(False);fig.colorbar(im,ax=ax,label='附加预测电量 / kWh',pad=.02,shrink=.85)
ax=axs[1,1];start=b0['costs']['total_yuan']/1e4;dp=(b2['costs']['planned_yuan']-b0['costs']['planned_yuan'])/1e4;du=(b2['costs']['emergency_yuan']-b0['costs']['emergency_yuan'])/1e4;end=b2['costs']['total_yuan']/1e4
for i,base,height,col in [(0,0,start,GREY),(1,start,dp,GOLD),(2,end,-du,TEAL),(3,0,end,BLUE)]:ax.bar(i,height,bottom=base,color=col,width=.6)
for i,v in [(0,start),(1,start+dp),(2,end)]:ax.plot([i+.3,i+.7],[v,v],color=GREY,lw=.7,ls=':')
for i,y,text in [(0,start,f'{start:.2f}'),(1,start+dp,f'+{dp:.2f}'),(2,end-du,f'{du:.2f}'),(3,end,f'{end:.2f}')]:ax.text(i,y+30,text,ha='center',fontsize=9)
ax.set_ylim(0,2100);ax.set_xticks(range(4),['B0总费','计划费增加','应急费减少','B2总费']);panel(ax,'d','费用变化闭合：额外计划电量换取应急减少',None,'费用 / 万元')
save(fig,'margin_mechanism','安全裕量的分布、选型与费用机制','a为一月8—31日事后描述，核密度逐组归一化峰高；不作为实时控制输入。b为8个实测组合，无插值；c为当时已可用历史形成的真实裕量。',{'january_residual_groups':[x.tolist() for x in groups],'empirical_q80':q80,'january_grid_wanyuan':mat.tolist(),'rolling_correction_kwh':corr.tolist(),'waterfall_wanyuan':[start,dp,du,end]})
# 3. Strict battery control: prescribed day, reachability envelope and full-year emergency surface.
fig,axs=fig4();d='2025-06-21';r=next(z for z in b2r if z['day']==d);idx=int(np.where(dates==d)[0][0]);z=r['schedule'];bounds=np.arange(145)/6
with source('data/processed/team_delivery/day_base.csv').open() as f:pr=list(csv.DictReader(f))
print('day_base columns',pr[0].keys());price=np.array([float(x['price_yuan_per_kwh']) if 'price_yuan_per_kwh' in x else float(x['price']) for x in pr]) if ('price_yuan_per_kwh' in pr[0] or 'price' in pr[0]) else np.array(js('analysis/real_q1_candidate/result.json')['report']['input']['price_yuan_per_kwh'])
ax=axs[0,0];ax.plot(hours,(L-V)[idx]*6/1000,color=BLUE,label='实际净负荷');ax.plot(hours,(L[idx-7]-V[idx-1])*6/1000,color=GREY,ls='--',label='基础预测');ax.plot(hours,(L[idx-7]-V[idx-1]+np.array(r['margin']['correction_kwh']))*6/1000,color=GOLD,ls='-.',label='含裕量预测');ax.axhline(0,color=GREY,lw=.6);ax.legend(ncol=3,fontsize=8,frameon=False);panel(ax,'a',d+'：预测与实际净负荷','物理时刻 / h','功率 / MW')
ax=axs[0,1];C=np.array(z['C']);DD=np.array(z['D']);ax.bar(hours,C,width=1/6,color=TEAL,label='充电');ax.bar(hours,-DD,width=1/6,color=BLUE,label='放电');ax.step(np.arange(145)/6,np.r_[z['U'],z['U'][-1]],where='post',color=RED,lw=1.3,label='应急购电');ax.legend(ncol=3,fontsize=8,frameon=False);panel(ax,'b','槽首动作与槽末应急结算','物理时刻 / h','电量 / kWh')
ax=axs[1,0];n=144-np.arange(145);lo=np.maximum(1200,6000-n*.9*5000/6)/1000;hi=np.minimum(10800,6000+n*5000/6/.9)/1000;ax.fill_between(bounds,lo,hi,color=TEAL,alpha=.13,label='仅功率/SOC约束下可达区域');ax.plot(bounds,z['E']/np.array(1000),color=BLUE,lw=1.5,label='实际储电量');ax.plot(bounds,lo,color=GREY,ls=':',lw=.9);ax.plot(bounds,hi,color=GREY,ls=':',lw=.9);ax.plot([0,24],[6,6],'o',mfc='white',mec=BLUE,ms=4);ax.legend(loc='upper center',fontsize=8,frameon=False);ax.set_ylim(0,12);panel(ax,'c','日终恢复约束与储电量轨迹','物理时刻 / h','储电量 / MWh')
ax=axs[1,1];u=np.array([x['schedule']['U'] for x in b2r]);monthmat=np.array([np.mean(u[[x['day'][5:7]==f'{m:02}' for x in b2r]],axis=0) for m in range(2,13)]);im=ax.imshow(monthmat,extent=(0,24,12.5,1.5),aspect='auto',cmap='YlOrRd',interpolation='nearest');ax.set_yticks(range(2,13));panel(ax,'d','全年应急购电的时段集中性','物理时刻 / h','月份');ax.grid(False);fig.colorbar(im,ax=ax,pad=.02,shrink=.85,label='日均每槽应急电量 / kWh')
for ax in axs.flat:ax.set_xticks(range(0,25,6));ax.set_xlim(0,24)
save(fig,'dispatch_mechanism','严格因果控制、终端约束与应急集中性','示例日为题面指定的6月21日，非事后筛选的最优日；右下图每格是当月同一槽的日均应急电量，含零应急日。',{'example_day':d,'schedule':z,'reachable_min_mwh':lo.tolist(),'reachable_max_mwh':hi.tolist(),'monthly_mean_emergency_kwh':monthmat.tolist()})
# 4. Stability: paired daily scatter, monthly violins, cumulative benefit and emergency survival.
fig,axs=fig4();a=np.array([x['costs']['total_yuan'] for x in b0r]);b=np.array([x['costs']['total_yuan'] for x in b2r]);delta=a-b;good=delta>1e-5
ax=axs[0,0];ax.scatter(a[good]/1e4,b[good]/1e4,s=15,color=BLUE,alpha=.6,label=f'费用下降：{good.sum()}日');ax.scatter(a[~good]/1e4,b[~good]/1e4,s=20,marker='x',color=RED,label=f'未下降：{(~good).sum()}日');lim=max(a.max(),b.max())/1e4*1.05;ax.plot([0,lim],[0,lim],color=GREY,ls='--',lw=.8,label='费用相等');ax.set_xlim(0,lim);ax.set_ylim(0,lim);ax.legend(fontsize=9,frameon=False);panel(ax,'a','逐日成对比较：对角线下方表示改进','B0日总费 / 万元','B2日总费 / 万元')
ax=axs[0,1];groups=[delta[[r['day'][5:7]==f'{m:02}' for r in b2r]]/1000 for m in range(2,13)];v=ax.violinplot(groups,positions=range(2,13),widths=.78,showextrema=False,showmedians=True)
for body in v['bodies']:body.set_facecolor(TEAL);body.set_edgecolor(TEAL);body.set_alpha(.35)
v['cmedians'].set_color(BLUE);ax.axhline(0,color=GREY,lw=.8);ax.set_xticks(range(2,13));panel(ax,'b','各月逐日节省的分布','月份','B0 − B2 / 千元')
ax=axs[1,0];cum=np.cumsum(delta)/1e4;ax.plot(np.arange(334),cum,color=BLUE,lw=1.6);ax.fill_between(np.arange(334),0,cum,color=BLUE,alpha=.09);ax.set_xticks(tick,[str(int(b2r[i]['day'][5:7])) for i in tick]);ax.set_xlim(0,333);ax.text(.98,.05,f'全年净节省 {cum[-1]:.2f} 万元',transform=ax.transAxes,ha='right',fontsize=10,color=BLUE);panel(ax,'c','累计节省轨迹','月份','累计节省 / 万元')
ax=axs[1,1]
for rr,label,col,ls in [(b0r,'B0',GREY,'--'),(b2r,'B2',BLUE,'-')]:
 vals=np.sort(np.array([x['costs']['emergency_yuan'] for x in rr])/1e4);ax.step(np.r_[0,vals],np.r_[1,1-np.arange(1,335)/334],where='post',label=label,color=col,ls=ls,lw=1.5)
ax.set_ylim(0,1.02);ax.legend(frameon=False);panel(ax,'d','应急费用经验超越概率','日应急费阈值 / 万元','高于阈值的天数占比')
save(fig,'strategy_stability','第二问收益分布与应急尾部','334天成对回放；小提琴图为核密度形状，横线为中位数；不作独立样本显著性推断。',{'dates':[r['day'] for r in b2r],'B0_total_yuan':a.tolist(),'B2_total_yuan':b.tolist(),'daily_saving_yuan':delta.tolist(),'improved_days':int(good.sum()),'monthly_daily_saving_thousand_yuan':[g.tolist() for g in groups]})
# 5. VOI decision geometry, posthoc diagnostic and final monthly realized outcome.
gates=[{'day':r['day'],**g} for r in ar for g in r['gates']];assert len(gates)==1002
pred=np.array([g['predicted_gain_yuan'] for g in gates]);adj=np.array([g['adjustment_yuan'] for g in gates]);emg_gain=pred+adj;accept=np.array([g['accept'] for g in gates]);post=np.array([g['posthoc_keep_variable_yuan']-g['posthoc_update_variable_yuan'] for g in gates]);assert accept.sum()==183;assert np.all(accept==(pred>500+1e-6))
fig,axs=fig4();ax=axs[0,0]
for mask,col,mk,label in [(~accept,GREY,'x','保持合同'),(accept,BLUE,'o','接受更新')]:ax.scatter(adj[mask]/1000,emg_gain[mask]/1000,s=16,marker=mk,color=col,alpha=.5,label=label)
lims=[min(adj.min(),emg_gain.min())/1000-1,max(adj.max(),emg_gain.max())/1000+1];ax.plot(lims,np.array(lims)+.5,color=RED,ls='--',lw=1,label='决策边界：应急节省 − 调整费 = 500元');ax.legend(fontsize=8,frameon=False,loc='upper left');panel(ax,'a','更新决策的费用几何','净合同调整费 / 千元','预计应急费节省 / 千元')
ax=axs[0,1]
for mask,col,mk,label in [(~accept,GREY,'x','保持'),(accept,BLUE,'o','更新')]:ax.scatter(pred[mask]/1000,post[mask]/1000,s=15,marker=mk,color=col,alpha=.45,label=label)
ax.axvline(.5,color=RED,ls='--',lw=.8);ax.axhline(0,color=GREY,lw=.8);ax.legend(ncol=2,fontsize=8,frameon=False);panel(ax,'b','预计净收益与事后固定延续对照','预计净收益 / 千元','事后固定延续净收益 / 千元')
ax=axs[1,0];ct=np.array([[sum(g['first_slot']==s and g['accept'] for g in gates),sum(g['first_slot']==s and not g['accept'] for g in gates)] for s in [36,72,108]])
ax.bar(range(3),ct[:,0],color=BLUE,label='接受');ax.bar(range(3),ct[:,1],bottom=ct[:,0],color='#DCE2E7',label='保持')
for i,n in enumerate(ct[:,0]):ax.text(i,350,f'{n}/334',ha='center',fontsize=10)
ax.set_ylim(0,450);ax.set_xticks(range(3),['06:00','12:00','18:00']);ax.legend(ncol=2,frameon=False,fontsize=9,loc='upper center');panel(ax,'c','各预报发布时间的更新接受情况','发布时间','机会次数')
ax=axs[1,1];months=sorted(voi['monthly_total_yuan']);vals=np.array([q3['margin_zero']['monthly_total_yuan'][m]-voi['monthly_total_yuan'][m] for m in months])/1000;ax.bar(range(11),vals,color=[BLUE if v>=0 else GOLD for v in vals]);ax.axhline(0,color=GREY,lw=.7);ax.set_xticks(range(11),[str(int(m[-2:])) for m in months]);panel(ax,'d',f'完整策略实测：全年仅净省 {sum(vals):.2f} 千元','月份','固定 − 门控总费 / 千元')
save(fig,'gate_decisions','第三问更新边界、估值误差与实测净收益','b为每次决策至日末固定合同的反事实预演，时域重叠，不可累加成策略全年收益；d才是完整实际策略的月度账本差。',{'decisions':[{'day':g['day'],'time':g['decision_time'],'predicted_gain_yuan':float(pred[i]),'adjustment_yuan':float(adj[i]),'predicted_emergency_saving_yuan':float(emg_gain[i]),'accepted':bool(accept[i]),'posthoc_frozen_gain_yuan':float(post[i])} for i,g in enumerate(gates)],'acceptance_by_issue':ct.tolist(),'monthly_realized_saving_thousand_yuan':vals.tolist()})
atlas.close()
for name,data in tables.items():(O/(name+'.data.json')).write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')))
manifest={'status':'candidate_v2_not_final','time_semantics':'physical slots 00:00-24:00; right-end sample candidate; official template offset unresolved','no_new_optimization':True,'sources':sources,'figures':metadata}
for row in metadata:row['sha256']=hashlib.sha256((O/row['file']).read_bytes()).hexdigest()
(O/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps({'plates':len(metadata),'accepted_gates':int(accept.sum()),'B2_improved_days':int(good.sum()),'B2_saving_yuan':float(delta.sum())},ensure_ascii=False))
