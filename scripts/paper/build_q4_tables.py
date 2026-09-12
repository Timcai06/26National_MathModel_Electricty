"""Generate the Q4 strict-transfer tables for the paper from verified results only."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import hashlib

Q4 = ROOT / 'analysis/strict_q4_transfer_v1'
TEX = ROOT / 'deliverables/draft_v5/latex/generated'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def table(name, headers, rows, align):
    text = ('\\begin{tabular}{' + align + '}\n\\toprule\n' + ' & '.join(headers)
            + ' \\\\\n\\midrule\n'
            + '\n'.join(' & '.join(map(str, r)) + ' \\\\' for r in rows)
            + '\n\\bottomrule\n\\end{tabular}\n')
    (TEX / (name + '.tex')).write_text(text, encoding='utf-8')


def main():
    report = json.loads((Q4 / 'result.json').read_text())
    check = json.loads((Q4 / 'independent_validation.json').read_text())
    if not check['passed'] or check['result_sha256'] != sha(Q4 / 'result.json'):
        raise ValueError('Q4 result lacks a current independent validation')
    if not check['emergency_invariance']['holds'] or check['margin_retuned_for_q4']:
        raise ValueError('Q4 protocol assertions not satisfied')
    TEX.mkdir(parents=True, exist_ok=True)

    money = lambda v: f'{v:,.2f}'
    q42 = report['q4-2']
    table('q4_2_costs', ['方案', '计划费/元', '应急费/元', '总费/元', '应急电量/kWh'],
          [[label] + [money(q42[key]['costs'][f]) for f in ('planned_yuan', 'emergency_yuan', 'total_yuan')]
           + [f"{q42[key]['emergency_kwh']:,.0f}"]
           for key, label in (('B0', 'B0 无裕量'), ('B2', 'B2 安全裕量'))], 'lrrrr')

    q43 = report['q4-3']
    labels = (('base_zero', '基线零点固定'), ('base_stale', '基线旧PV更新'), ('base_fresh', '基线新PV更新'),
              ('margin_zero', '裕量零点固定'), ('margin_stale', '裕量旧PV更新'), ('margin_fresh', '裕量新PV更新'))
    table('q4_3_costs', ['方案', '计划费/万元', '调整费/万元', '应急费/万元', '总费/万元'],
          [[label] + [f"{q43[key]['costs'][f] / 1e4:.4f}"
                      for f in ('planned_yuan', 'adjustment_yuan', 'emergency_yuan', 'total_yuan')]
           for key, label in labels], 'lrrrr')

    fixed = {
        'Q2 B0': json.loads((ROOT / 'analysis/strict_q2_round2_v1/result.json').read_text())['strategies']['B0'],
        'Q2 B2': json.loads((ROOT / 'analysis/q2_margin_oracle_v1/result.json').read_text())['strategies']['B2'],
    }
    q3fixed = json.loads((ROOT / 'analysis/strict_q3_transfer_v1/result.json').read_text())['strategies']
    pairs = [('Q2 基线 B0', fixed['Q2 B0'], q42['B0']),
             ('Q2 裕量 B2', fixed['Q2 B2'], q42['B2']),
             ('Q3 基线零点固定', q3fixed['base_zero'], q43['base_zero']),
             ('Q3 裕量零点固定', q3fixed['margin_zero'], q43['margin_zero']),
             ('Q3 裕量新PV更新', q3fixed['margin_fresh'], q43['margin_fresh'])]
    table('q4_vs_fixed', ['方案', '固定电价/元', '动态电价/元', '差额/元'],
          [[label, money(a['costs']['total_yuan']), money(b['costs']['total_yuan']),
            f"{b['costs']['total_yuan'] - a['costs']['total_yuan']:+,.2f}"] for label, a, b in pairs], 'lrrr')

    print('Q4 tables written to', TEX.relative_to(ROOT))


if __name__ == '__main__':
    main()
