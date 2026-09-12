"""Source-linked standalone figures for the conditional known-price experiment."""
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scripts.run_real_q4 import OUT
from scripts.run_real_q23 import dump


def main():
    report = json.loads((OUT/'result.json').read_text())
    checked = json.loads((OUT/'independent_validation.json').read_text())
    if not checked['passed'] or checked['result_sha256'] != hashlib.sha256((OUT/'result.json').read_bytes()).hexdigest():raise ValueError('Unvalidated results')
    names = ['q4_2_main','q4_3_zero_only','q4_3_stale_updates','q4_3_main']
    labels = ['Q4-2 day-ahead','Q4-3 midnight only','Q4-3 replan / stale PV','Q4-3 fresh updates']
    fig,ax = plt.subplots(figsize=(10,4.5),layout='constrained')
    left = np.zeros(4)
    for key,label,color in [('planned_yuan','Initial plan','#436587'),('adjustment_yuan','Net adjustment','#e4ad59'),('emergency_yuan','Emergency purchase','#c66b65')]:
        values = np.array([report['strategies'][n]['costs'][key]/1e6 for n in names])
        ax.barh(np.arange(4),values,left=left,label=label,color=color,height=.55);left += values
    for i,v in enumerate(left):ax.text(v+.08,i,f'{v:.3f}',va='center')
    ax.set_yticks(np.arange(4),labels);ax.invert_yaxis();ax.set_xlim(0,18)
    ax.set_xlabel('Realized cost (million yuan), Feb–Dec 2025')
    ax.set_title('Q4 candidates: full daily price curve assumed known at midnight',loc='left')
    ax.spines[['top','right']].set_visible(False)
    ax.legend(loc='lower left',bbox_to_anchor=(0,-.4),ncol=3,frameon=False)
    files=[]
    for suffix in ('png','svg'):
        p=OUT/f'cost_comparison.{suffix}';fig.savefig(p,dpi=160);files.append(p)
    plt.close(fig)
    fig,axes = plt.subplots(1,2,figsize=(10,4.5),layout='constrained')
    for n,ax in zip((2,3),axes):
        c=report['repricing_controls'][str(n)]
        costs=[c['old_actions_at_dynamic_prices_yuan']/1e6,c['dynamic_reoptimized_cost_yuan']/1e6]
        ax.bar(['Old actions\nrepriced','Dynamic-price\nreoptimization'],costs,color=['#9ca9b2','#436587'],width=.6)
        for i,v in enumerate(costs):ax.text(i,v+.1,f'{v:.3f}',ha='center')
        ax.set_ylim(0,18);ax.set_ylabel('Cost (million yuan)');ax.set_title(f'Q4-{n}: same dynamic prices',loc='left')
        ax.spines[['top','right']].set_visible(False)
    fig.suptitle('Separate the price environment from changes in dispatch actions')
    for suffix in ('png','svg'):
        p=OUT/f'repricing_control.{suffix}';fig.savefig(p,dpi=160);files.append(p)
    plt.close(fig)
    dump(OUT/'figure_manifest.json',{'source_sha256':hashlib.sha256((OUT/'result.json').read_bytes()).hexdigest(),
        'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}})


if __name__ == '__main__':main()
