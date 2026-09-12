"""Monthly mean battery state surface from existing B2 trajectories."""
from pathlib import Path
import os,json,hashlib
R=Path(__file__).resolve().parents[2];os.environ.setdefault('MPLCONFIGDIR',str(R/'tmp/matplotlib'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.colors import LinearSegmentedColormap,Normalize
fm.fontManager.addfont('/System/Library/Fonts/Supplemental/Arial Unicode.ttf');plt.rcParams.update({'font.family':['Arial Unicode MS','DejaVu Sans'],'font.size':10,'axes.unicode_minus':False,'pdf.fonttype':42})
O=R/'deliverables/candidate_figures/v3_3d';O.mkdir(exist_ok=True);p=R/'analysis/q2_margin_oracle_v1/B2.jsonl';rows=[json.loads(x) for x in p.open()];assert len(rows)==334
Z=np.array([np.mean([r['schedule']['E'] for r in rows if r['day'][5:7]==f'{m:02}'],axis=0)/1000 for m in range(2,13)]);assert Z.shape==(11,145);assert np.allclose(Z[:,[0,-1]],6);assert Z.min()>=1.2-1e-8 and Z.max()<=10.8+1e-8
X,Y=np.meshgrid(np.arange(145)/6,np.arange(2,13));cmap=LinearSegmentedColormap.from_list('soc',['#F4F8F8','#BFDCDA','#73ACAA','#316A74']);norm=Normalize(1.2,10.8)
fig=plt.figure(figsize=(11.8,5.3));gs=fig.add_gridspec(1,2,width_ratios=[1.12,1],left=.03,right=.91,bottom=.14,top=.86,wspace=.28);a=fig.add_subplot(gs[0],projection='3d');b=fig.add_subplot(gs[1]);a.set_proj_type('ortho');a.view_init(27,-125)
a.plot_surface(X,Y,Z,cmap=cmap,norm=norm,rcount=11,ccount=145,linewidth=0,antialiased=True);a.plot_wireframe(X,Y,Z,rstride=1,cstride=12,color='#E6EFED',linewidth=.5,alpha=.8);a.contour(X,Y,Z,zdir='z',offset=0,levels=[2,4,6,8,10],cmap=cmap,norm=norm,linewidths=.7)
a.set(xlabel='物理时刻 / h',ylabel='月份',zlabel='平均储电量 / MWh',zlim=(0,12));a.set_xticks([0,6,12,18,24]);a.set_yticks([2,4,6,8,10,12]);a.tick_params(labelsize=8,pad=1);a.set_box_aspect((1.2,1,.7));a.set_title('a  日内调控与月份的储电量曲面',loc='left',pad=18)
for axis in [a.xaxis,a.yaxis,a.zaxis]:axis.pane.fill=False;axis._axinfo['grid']['color']=(.84,.87,.9,.6)
b.contourf(X,Y,Z,levels=np.linspace(1.2,10.8,17),cmap=cmap,norm=norm);cs=b.contour(X,Y,Z,levels=[2,4,6,8,10],colors='#587F85',linewidths=.6);b.clabel(cs,inline=True,fontsize=8,fmt='%.0f');b.set(xlabel='物理时刻 / h',ylabel='月份',xlim=(0,24),ylim=(2,12));b.set_xticks([0,4,8,12,16,20,24]);b.set_yticks(range(2,13));b.set_title('b  同一储电量场的等高线投影',loc='left',pad=18)
cax=fig.add_axes([.935,.18,.016,.61]);fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),cax=cax,label='平均储电量 / MWh');fig.text(.06,.025,'2025年2—12月B2实际控制轨迹：先按月逐边界取日均，再连接网格；日初日末均为6 MWh。',fontsize=10,color='#576571')
for ext in ['pdf','png']:fig.savefig(O/f'q2_soc_monthly_3d.{ext}',dpi=200,bbox_inches='tight')
plt.close(fig);np.savetxt(O/'soc_monthly_grid.csv',np.column_stack([Y.ravel(),X.ravel(),Z.ravel()]),delimiter=',',header='month,physical_hour,mean_stored_mwh',comments='')
(O/'soc_manifest.json').write_text(json.dumps({'source':str(p.relative_to(R)),'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'status':'candidate descriptive monthly mean, not a trajectory or new optimized policy','shape':[11,145],'averaging':'equal daily weights within month','physical_bounds_checked':True,'endpoints_checked':True,'mesh_interpolation':'adjacent month/hour nodes connected for visualization only'},ensure_ascii=False,indent=2));print('SOC 3D panel: 11 x 145 verified grid nodes')
