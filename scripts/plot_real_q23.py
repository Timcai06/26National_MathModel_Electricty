"""Standalone candidate figures drawn only from independently verified results."""
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scripts.run_real_q23 import OUT, dump


def main():
    report = json.loads((OUT/'result.json').read_text())
    validation = json.loads((OUT/'independent_validation.json').read_text())
    if not validation['passed'] or validation['result_sha256'] != hashlib.sha256((OUT/'result.json').read_bytes()).hexdigest():
        raise ValueError('Unvalidated results')
    names = ['q2_yesterday','q2_last_week','q2_main','q3_zero_only','q3_update_6',
             'q3_update_12','q3_update_18','q3_stale_updates','q3_main','q3_step','q3_no_refund']
    labels = ['Q2 yesterday','Q2 last week','Q2 January-selected', 'Q3 midnight only',
              'Q3 update 06:00','Q3 update 12:00','Q3 update 18:00','Q3 replan / stale PV',
              'Q3 all fresh updates','Q3 step conversion','Q3 no-refund sensitivity']
    fig, ax = plt.subplots(figsize=(11,6.5), layout='constrained')
    x = np.arange(len(names))
    left = np.zeros(len(names))
    for field, label, color in [('planned_yuan','Initial plan','#436587'),
                              ('adjustment_yuan','Net adjustment','#e4ad59'),
                              ('emergency_yuan','Emergency purchase','#c66b65')]:
        values = np.array([report['strategies'][n]['costs'][field]/1e6 for n in names])
        ax.barh(x, values, left=left, label=label, color=color, height=.65)
        left += values
    for i, total in enumerate(left):
        ax.text(total+.12,i,f'{total:.3f}', va='center',fontsize=9)
    ax.set_yticks(x,labels); ax.invert_yaxis(); ax.set_xlim(0,25)
    ax.set_xlabel('Realized cost (million yuan), Feb 1–Dec 31, 2025')
    ax.set_title('Q2 / Q3 candidate strategies under common execution assumptions', loc='left')
    ax.legend(loc='lower right',frameon=False)
    ax.spines[['top','right']].set_visible(False)
    files = []
    for suffix in ('png','svg'):
        p = OUT/f'cost_comparison.{suffix}';fig.savefig(p,dpi=160);files.append(p)
    plt.close(fig)
    q2 = json.loads((OUT/'q2_main_selected_days.json').read_text())
    q3 = json.loads((OUT/'q3_main_selected_days.json').read_text())
    fig, axes = plt.subplots(2,2,figsize=(11,7),layout='constrained')
    for ax, day in zip(axes.flat,q2):
        for source, label, color in [(q2,'Q2','#436587'),(q3,'Q3','#c66b65')]:
            ax.plot(np.arange(145)/6,source[day]['schedule']['E'], label=label,color=color,lw=1.5)
        for hour in (6,12,18):ax.axvline(hour,color='#999999',ls=':',lw=.7)
        ax.set_title(day,loc='left');ax.set_xlim(0,24);ax.set_ylim(0,12000)
        ax.set_xlabel('Hour');ax.set_ylabel('Stored energy (kWh)')
        ax.spines[['top','right']].set_visible(False)
    axes[0,0].legend(frameon=False)
    fig.suptitle('Realized storage trajectories — candidate daily-neutral policy')
    for suffix in ('png','svg'):
        p=OUT/f'selected_storage.{suffix}';fig.savefig(p,dpi=160);files.append(p)
    plt.close(fig)
    dump(OUT/'figure_manifest.json', {'source_sha256':hashlib.sha256((OUT/'result.json').read_bytes()).hexdigest(),
        'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}})


if __name__ == '__main__':main()
