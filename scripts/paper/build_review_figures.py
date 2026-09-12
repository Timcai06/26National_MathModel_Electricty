"""Publication figures from existing results; no model fitting or optimization."""
from pathlib import Path
import os
import sys
import json
import hashlib
from datetime import timedelta

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'tmp/matplotlib'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import FancyBboxPatch

OUT = ROOT / 'paper/figures'
OUT.mkdir(parents=True, exist_ok=True)
font_manager.fontManager.addfont('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
NAVY, TEAL, GOLD, RED, GRAY = '#214F70', '#258C96', '#E5B85C', '#C86A59', '#617784'
CMAP = LinearSegmentedColormap.from_list('ocean_sun', ['#275D92', '#32A5B3', '#94CEBB', '#F3DF8C', '#EBA25D'])
plt.rcParams.update({'font.family': ['Arial Unicode MS', 'DejaVu Sans'], 'font.size': 11,
                     'axes.unicode_minus': False, 'pdf.fonttype': 42,
                     'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.labelcolor': NAVY, 'text.color': NAVY, 'axes.edgecolor': '#BAC9D0',
                     'xtick.color': GRAY, 'ytick.color': GRAY})
SOURCES = {}
def read(name):
    path = ROOT / name
    SOURCES[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text())

def save(fig, name):
    for ext in ['pdf', 'png']:
        fig.savefig(OUT / f'{name}.{ext}', dpi=230, bbox_inches='tight', pad_inches=.16)
    plt.close(fig)

def surface_style(ax, xlabel, ylabel, zlabel, aspect=(1.25, 1, .65)):
    ax.set_proj_type('ortho')
    ax.set(xlabel=xlabel, ylabel=ylabel, zlabel=zlabel)
    ax.set_box_aspect(aspect)
    ax.tick_params(labelsize=10, pad=1)
    for axis in [ax.xaxis, ax.yaxis, ax.zaxis]:
        axis.pane.fill = False
        axis._axinfo['grid']['color'] = (.80, .86, .89, .55)

def representative_day():
    result=read('analysis/real_q1_candidate/result.json')['report']
    s=result['comparison']['strategies']['optimized']['schedule']
    h=np.arange(145)/6
    def boundary(values): return np.r_[values,values[-1]]
    fig,axes=plt.subplots(3,1,figsize=(10.6,6.4),sharex=True)
    fig.subplots_adjust(left=.10,right=.97,bottom=.10,top=.96,hspace=.30)
    a,b,c=axes
    for values,color,label in [(result['input']['load_kwh'],NAVY,'小区负荷'),(result['input']['pv_forecast_kwh'],GOLD,'光伏发电')]:
        a.step(h,boundary(np.asarray(values)*6/1000),where='post',color=color,lw=1.6,label=label)
    a.set_ylabel('功率 / MW'); a.set_title('A  负荷与光伏出力',loc='left',fontsize=12)
    a.legend(ncol=2,frameon=False,fontsize=10,loc='upper left')
    b.step(h,boundary(np.asarray(s['G'])/1000),where='post',color=GRAY,lw=1,label='计划购电')
    b.fill_between(h,boundary(np.asarray(s['C'])/1000),step='post',color=TEAL,alpha=.7,label='充电')
    b.fill_between(h,boundary(-np.asarray(s['D'])/1000),step='post',color=RED,alpha=.7,label='放电（负向）')
    b.set_ylabel('时段电量 / MWh'); b.set_title('B  购电与充放电安排',loc='left',fontsize=12)
    b.legend(ncol=3,frameon=False,fontsize=10,loc='upper left'); b.axhline(0,color=GRAY,lw=.5)
    c.plot(h,np.asarray(s['E'])/1000,color=NAVY,lw=1.7)
    c.axhspan(1.2,10.8,color=TEAL,alpha=.055)
    for v in [1.2,10.8]:c.axhline(v,color=GRAY,lw=.8,ls='--')
    c.scatter([0,24],[6,6],s=25,color=RED,zorder=5)
    c.set(xlabel='日内时刻 / h',ylabel='储电量 / MWh',ylim=(.5,11.6)); c.set_title('C  储电量轨迹与运行边界',loc='left',fontsize=12)
    for ax in axes:ax.set_xlim(0,24); ax.set_xticks(range(0,25,4)); ax.grid(axis='y',alpha=.13)
    save(fig,'representative_dispatch')

def response():
    report = read('analysis/q2_january_surface_v1/result.json')
    validation = read('analysis/q2_january_surface_v1/validation.json')
    assert validation['passed'] and validation['day_replays_verified'] == 1377
    rows = report['scores']; taus = sorted({r['tau'] for r in rows}); scales = sorted({r['scale'] for r in rows})
    grid = {(r['tau'], r['scale']): r['total_yuan']/1e4 for r in rows}
    X, Y = np.meshgrid(taus, scales); Z = np.array([[grid[t,k] for t in taus] for k in scales])
    assert Z.shape == (9, 9)
    fixed = grid[.8,1.]; floor = Z.min() - .7; norm = Normalize(Z.min(), Z.max())
    fig = plt.figure(figsize=(10.6, 8.5))
    ax = fig.add_axes([.06,.35,.81,.62], projection='3d', computed_zorder=False)
    ax.view_init(25, 48)
    ax.plot_surface(X,Y,Z,cmap=CMAP,norm=norm,rstride=1,cstride=1,edgecolor='#E7F3F0',linewidth=.65,alpha=.98)
    ax.contour(X,Y,Z,zdir='z',offset=floor,levels=10,cmap=CMAP,norm=norm,linewidths=.7)
    ax.scatter([.8],[1.],[fixed],marker='*',s=180,c=RED,edgecolors='white',linewidths=1,zorder=9,depthshade=False)
    ax.set_zlim(floor, Z.max()+.2)
    ax.set_xticks([.5,.6,.7,.8,.9]); ax.set_yticks([.25,.5,.75,1,1.25])
    surface_style(ax,'分位数水平 τ','裕量系数 κ','总费用 / 万元')
    fig.text(.055,.955,'A  参数变化下的购电费用响应',fontsize=13,weight='bold')
    cb = fig.add_axes([.90,.49,.018,.32]); fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=CMAP),cax=cb,label='17 天总费用 / 万元')
    fig.text(.61,.40,f'★ 固定参数 (0.80, 1.00)\n    {fixed:.3f} 万元',fontsize=11,color=RED)
    b = fig.add_axes([.09,.08,.37,.24]); c = fig.add_axes([.60,.08,.34,.24])
    b.contourf(X,Y,Z,levels=12,cmap=CMAP,norm=norm)
    contours=b.contour(X,Y,Z,levels=6,colors=NAVY,linewidths=.55); b.clabel(contours,fontsize=8,fmt='%.1f')
    b.scatter(X,Y,s=10,c=NAVY,alpha=.45); b.scatter([.8],[1],marker='*',s=120,c=RED,edgecolors='white',zorder=8)
    b.set(xlabel='分位数水平 τ',ylabel='裕量系数 κ'); b.set_title('B  同一网格的等高线',loc='left',fontsize=12,pad=12)
    for k,color in [(.5,GRAY),(.75,TEAL),(1.,RED)]:
        c.plot(taus,[grid[t,k] for t in taus],'-o',ms=3,lw=1.6,color=color,label=f'κ = {k:.2f}')
    c.set(xlabel='分位数水平 τ',ylabel='总费用 / 万元'); c.set_title('C  固定裕量系数的剖面',loc='left',fontsize=12,pad=12)
    c.grid(axis='y',alpha=.16); c.legend(fontsize=8,frameon=False)
    save(fig,'parameter_response')

def soc():
    p=ROOT/'analysis/q2_margin_oracle_v1/B2.jsonl'; SOURCES[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    rows=[json.loads(x) for x in p.open()]; assert len(rows)==334
    Z=np.array([np.mean([r['schedule']['E'] for r in rows if int(r['day'][5:7])==m],axis=0)/1000 for m in range(2,13)])
    assert Z.shape==(11,145) and np.allclose(Z[:,[0,-1]],6) and Z.min()>=1.2-1e-6 and Z.max()<=10.8+1e-6
    X,Y=np.meshgrid(np.arange(145)/6,np.arange(2,13)); norm=Normalize(1.2,10.8)
    fig=plt.figure(figsize=(10.6,6.9)); ax=fig.add_axes([.03,.23,.64,.72],projection='3d'); ax.view_init(28,-125)
    ax.plot_surface(X,Y,Z,cmap=CMAP,norm=norm,rcount=11,ccount=145,linewidth=0,antialiased=True)
    ax.plot_wireframe(X,Y,Z,rstride=1,cstride=12,color='#EFF8F6',linewidth=.55,alpha=.8)
    ax.contour(X,Y,Z,zdir='z',offset=0,levels=[2,4,6,8,10],cmap=CMAP,norm=norm,linewidths=.6)
    surface_style(ax,'日内时刻 / h','月份','平均储电量 / MWh'); ax.set_zlim(0,12)
    ax.set_xticks([0,6,12,18,24]); ax.set_yticks([2,4,6,8,10,12])
    fig.text(.04,.96,'A  全年储能调控的日内节律',fontsize=13,weight='bold')
    b=fig.add_axes([.74,.36,.19,.49]); b.contourf(X,Y,Z,levels=np.linspace(1.2,10.8,17),cmap=CMAP,norm=norm)
    b.set(xlabel='日内时刻 / h',ylabel='月份'); b.set_xticks([0,12,24]); b.set_yticks(range(2,13,2)); b.set_title('B  等高线投影',fontsize=12,pad=15)
    cb=fig.add_axes([.22,.15,.56,.022]); fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=CMAP),cax=cb,orientation='horizontal',label='平均储电量 / MWh')
    fig.text(.12,.025,'月内逐时点等权平均  ·  11 个月 × 145 个边界时点  ·  日初与日末均为 6 MWh',fontsize=11,color=GRAY)
    save(fig,'monthly_storage')

def rolling():
    from scripts.paper.build_advanced_figures import read_context, snapshot_commitment
    from src.q2.forecast import midnight
    context=read_context(); SOURCES.update({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in context['source_paths']})
    selected=context['q3_selected']['margin_fresh']['2025-06-21']; days=context['days']
    idx=next(i for i,d in enumerate(days) if str(d.day)=='2025-06-21'); day=days[idx]
    load=np.asarray(days[idx-7].load_kwh)+np.asarray(selected['margin']['correction_kwh'])
    net=(day.load_kwh-day.pv_kwh)/1000; final=np.asarray(selected['schedule']['G'])/1000
    x=np.arange(144)/6
    fig,axes=plt.subplots(1,4,figsize=(10.6,5.9),sharey=True)
    fig.subplots_adjust(left=.08,right=.98,top=.79,bottom=.35,wspace=.13)
    for ax,h in zip(axes,[0,6,12,18]):
        slot=h*6; issue=midnight(day.day)+timedelta(hours=h)
        pv=context['published'][issue].energy(decision_time=issue,method='linear')
        # PublishedPV starts at its issue time, not at midnight.
        forecast=(load[slot:]-np.asarray(pv)[:144-slot])/1000
        commitment=snapshot_commitment(selected,slot)/1000
        assert np.allclose(commitment[:slot],final[:slot],atol=1e-9,rtol=0)
        ax.axvspan(0,h,color=NAVY,alpha=.045); ax.axvspan(h,24,color=TEAL,alpha=.07)
        ax.step(x[:slot],net[:slot],where='post',color=NAVY,lw=1.1)
        ax.step(x[:slot],final[:slot],where='post',color=GRAY,lw=.8)
        ax.step(x[slot:],forecast,where='post',color=TEAL,lw=1.1,ls='--')
        ax.step(x[slot:],commitment[slot:],where='post',color=GOLD,lw=1.1)
        ax.axvline(h,color=RED,lw=.8,ls=':'); ax.set(xlim=(0,24),xlabel='时刻 / h')
        ax.set_xticks([0,6,12,18,24]); ax.tick_params(labelsize=9); ax.set_title(f'{h:02d}:00 更新',fontsize=12,loc='left')
        ax.grid(axis='y',alpha=.15)
    axes[0].set_ylabel('每时段电量 / MWh')
    from matplotlib.lines import Line2D
    fig.legend([Line2D([],[],color=c,lw=1.7,ls=ls) for c,ls in [(NAVY,'-'),(GRAY,'-'),(TEAL,'--'),(GOLD,'-')]],
               ['历史实际净负荷','历史锁定购电','当前预测净负荷','当前购电承诺'],loc='upper center',bbox_to_anchor=(.53,.93),ncol=4,frameon=False,fontsize=10)
    a=fig.add_axes([.06,.045,.90,.20]); a.axis('off'); a.set(xlim=(0,1),ylim=(0,1))
    labels=['已发布预报\n与当前储电量','余日合同优化\n计入调整成本','锁定本槽动作\n执行充放电','槽末观测与结算\n更新下一时段状态']
    for i,label in enumerate(labels):
        left=.01+i*.255; a.add_patch(FancyBboxPatch((left,.31),.215,.57,boxstyle='round,pad=.008',facecolor='#F4F8FA',edgecolor=[TEAL,TEAL,GOLD,NAVY][i],lw=.9))
        a.text(left+.1075,.59,label,ha='center',va='center',fontsize=10,linespacing=1.6)
        if i<3:a.annotate('',xy=(left+.25,.59),xytext=(left+.22,.59),arrowprops={'arrowstyle':'->','color':GRAY})
    a.plot([.88,.88,.11],[.30,.10,.10],color=TEAL,lw=.9,transform=a.transAxes)
    a.annotate('',xy=(.11,.30),xytext=(.11,.10),arrowprops={'arrowstyle':'->','color':TEAL,'lw':.9})
    a.text(.5,.02,'新信息仅进入后续决策；已执行时段保持不变',ha='center',fontsize=9,color=GRAY,bbox={'facecolor':'white','edgecolor':'none','pad':1})
    save(fig,'rolling_contract')

def prices():
    q2=read('analysis/q2_margin_oracle_v1/result.json')['strategies']; q4=read('analysis/strict_q4_transfer_v1/result.json')['q4-2']
    q2['B0']=read('analysis/strict_q2_round2_v1/result.json')['strategies']['B0']
    fig,axes=plt.subplots(1,2,figsize=(10.6,4.2),gridspec_kw={'width_ratios':[1,1.1]}); fig.subplots_adjust(left=.08,right=.98,bottom=.18,top=.84,wspace=.36)
    a,b=axes; groups=[q2['B0'],q2['B2'],q4['B0'],q4['B2']]; labels=['固定\n基线','固定\n安全裕量','动态\n基线','动态\n安全裕量']
    base=np.array([r['costs']['planned_yuan']/1e4 for r in groups]); emg=np.array([r['costs']['emergency_yuan']/1e4 for r in groups]); x=np.arange(4)
    a.bar(x,base,color=TEAL,width=.6,label='计划购电费'); a.bar(x,emg,bottom=base,color=GOLD,width=.6,label='紧急购电费')
    for i,v in enumerate(base+emg):a.text(i,v+20,f'{v:.1f}',ha='center',fontsize=9)
    a.set_xticks(x,labels); a.set_ylabel('334 天费用 / 万元'); a.set_ylim(0,2050); a.legend(frameon=False,fontsize=9,loc='upper left',ncol=2)
    a.set_title('A  两种电价下的费用构成',loc='left',fontsize=12,pad=14)
    for data,color,label in [(q2,NAVY,'固定电价'),(q4,TEAL,'动态电价')]:
        months=sorted(data['B0']['monthly_total_yuan']); savings=[(data['B0']['monthly_total_yuan'][m]-data['B2']['monthly_total_yuan'][m])/1e4 for m in months]
        b.plot(range(2,13),savings,'o-',ms=4,lw=1.7,color=color,label=label)
    b.set(xlabel='月份',ylabel='安全裕量节省 / 万元'); b.set_xticks(range(2,13)); b.grid(axis='y',alpha=.16); b.legend(frameon=False,fontsize=9)
    b.set_title('B  月度节省的迁移表现',loc='left',fontsize=12,pad=14)
    save(fig,'dynamic_price_comparison')

if __name__=='__main__':
    representative_day(); response(); soc(); rolling(); prices()
    SOURCES[str(Path(__file__).relative_to(ROOT))]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest={'sources':SOURCES,'figures':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('*.pdf')},
              'scope':'Existing results only; January surface is descriptive; rolling update is Q3 comparison strategy.'}
    manifest_path=ROOT/'tmp/pdfs/classmate_review/figure_manifest.json'
    manifest_path.parent.mkdir(parents=True,exist_ok=True)
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print('Five paper figures generated and source-bound.')
