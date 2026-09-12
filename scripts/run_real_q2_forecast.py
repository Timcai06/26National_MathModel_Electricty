"""Read audited annual data without cleaning; evaluate explicit availability candidates."""
import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from src.q2.forecast import ActualDay, midnight
from src.q2.backtest import walk_forward


def parse_days(rows, *, delay_minutes):
    if type(delay_minutes) is not int or delay_minutes < 0:
        raise ValueError('Explicit nonnegative availability delay required')
    first = date(2025, 1, 1)
    if len(rows) != 365 * 144:
        raise ValueError('Expected complete 2025 annual data; no filling')
    days = []
    for index in range(365):
        day = first + timedelta(days=index)
        block = rows[index * 144:(index + 1) * 144]
        for slot, row in enumerate(block):
            label = (midnight(day) + timedelta(minutes=10*(slot+1))).strftime('%H:%M:%S')
            if slot == 143:
                label = '0:00+1'
            if row['date'] != day.isoformat() or int(row['slot']) != slot or row['time_str'] != label:
                raise ValueError('Date/slot/endpoint label mismatch; no sorting or remapping')
            for kw, kwh in [('load_kw', 'load_kwh'), ('pv_actual_kw', 'pv_actual_kwh')]:
                values = [float(row[kw]), float(row[kwh])]
                if not all(np.isfinite(v) and v >= 0 for v in values) or abs(values[0]/6-values[1]) > 1e-8:
                    raise ValueError('Invalid value or unit mismatch')
        days.append(ActualDay(day, [float(r['load_kwh']) for r in block],
            [float(r['pv_actual_kwh']) for r in block],
            midnight(day) + timedelta(days=1, minutes=delay_minutes)))
    return days


def load_rows():
    source = ROOT / 'data/processed/team_delivery/annual_actual.csv'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    audit = json.loads((ROOT / 'analysis/team_delivery/intake_audit.json').read_text())
    if audit['input_sha256'].get(str(source.relative_to(ROOT))) != digest:
        raise ValueError('Annual CSV changed since intake audit')
    if audit['source_comparisons']['annual_actual']['mismatches_above_1e-8'] != 0:
        raise ValueError('Annual source comparison failed')
    with source.open(newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    return rows, source, digest


def main():
    rows, source, digest = load_rows()
    output = ROOT / 'analysis/real_q2_forecast_candidate'
    output.mkdir(parents=True, exist_ok=True)
    summaries = {}
    for delay in (0, 10):
        days = parse_days(rows, delay_minutes=delay)
        report = walk_forward(days, start_day=date(2025, 1, 8), end_day=date(2025, 12, 31),
            metadata=dict(input_kind='standardized', data_version='sha256:'+digest,
                mapping_version='endpoint-144-candidate-v1',
                assumptions_version=f'whole-day-available-after-{delay}min-candidate-v1'))
        # Independently score exact calendar lags on the shared evaluation range.
        for method, lag in [('yesterday', 1), ('last_week', 7)]:
            expected_days = 0 if delay > 0 and lag == 1 else 358
            summary = report['summary'][method]
            if summary['scored_days'] != expected_days:
                raise RuntimeError('Unexpected causal coverage')
            if expected_days:
                for field in ('load', 'pv'):
                    residual = np.concatenate([getattr(days[i-lag], field+'_kwh') -
                        getattr(days[i], field+'_kwh') for i in range(7, 365)])
                    expected = (np.abs(residual).mean(), np.sqrt(np.mean(residual**2)))
                    actual = summary[field]
                    if not np.allclose(expected, [actual['mae_kwh_per_slot'], actual['rmse_kwh_per_slot']], rtol=0, atol=1e-10):
                        raise RuntimeError('Independent error check failed')
        # Daily audit table retains publication evidence and scores, not duplicate arrays.
        with (output / f'daily_delay_{delay}min.csv').open('w', newline='') as f:
            fields = ['day', 'method', 'status', 'issue_time', 'source_day', 'source_available_at',
                      'history_days_available', 'load_mae', 'load_rmse', 'pv_mae', 'pv_rmse']
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in report['rows']:
                compact = {key: row[key] for key in fields[:7]}
                for field in ('load', 'pv'):
                    for metric in ('mae', 'rmse'):
                        compact[f'{field}_{metric}'] = row.get(field+'_metrics', {}).get(metric+'_kwh_per_slot')
                writer.writerow(compact)
        summaries[str(delay)] = {'status': report['status'], 'metadata': report['metadata'],
            'summary': report['summary'], 'independent_metrics_passed': True,
            'fair_accuracy_comparison': all(v['scored_days'] == 358 for v in report['summary'].values())}
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise RuntimeError('Source unexpectedly changed')
    result = {'scope': 'real forecast candidate only; availability assumed, not Gate 3 or realized cost acceptance',
        'source': str(source.relative_to(ROOT)), 'source_sha256': digest, 'source_unchanged': True,
        'evaluation_start': '2025-01-08', 'evaluation_end': '2025-12-31', 'evaluation_days': 358,
        'historical_days': 7, 'physical_warmup_performed': False, 'semantic_acceptance': False,
        'scenarios': summaries,
        'code_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__).resolve(), ROOT/'src/q2/forecast.py', ROOT/'src/q2/backtest.py', ROOT/'src/core/model.py']}}
    (output/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
