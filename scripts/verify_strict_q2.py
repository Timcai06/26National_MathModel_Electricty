"""Independent saved-trace physics, fee, chronology and paired-G audit."""
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from scripts.run_strict_q2 import OUT
from scripts.run_real_q23 import audited_csv, dump
from scripts.run_real_q2_forecast import load_rows, parse_days
from scripts.verify_real_q23 import check_day
from src.q2.forecast import midnight


def verify():
    report = json.loads((OUT/'result.json').read_text())
    for p, digest in {**report['input_sha256'], **report['code_sha256']}.items():
        if hashlib.sha256((ROOT/p).read_bytes()).hexdigest() != digest:
            raise ValueError('Input/code changed: '+p)
    rows, _, _ = load_rows()
    days = parse_days(rows, delay_minutes=0)
    days_by_date = {str(day.day): day for day in days}
    prices, _ = audited_csv('data/processed/team_delivery/day_base.csv')
    price = np.array([float(r['price']) for r in prices])
    evidence, commitments = {}, []
    for mode in ('B0', 'B1'):
        path = OUT/f'{mode}.jsonl'
        expected = report['strategies'][mode]
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected['daily_file_sha256']:
            raise ValueError('Trace hash mismatch')
        state, worst, warmup = 6000., 0., 0.
        totals = dict.fromkeys(expected['costs'], 0.)
        months = {}
        predicted_emergency, predicted_emergency_slots = 0., 0
        count = 0
        for i, line in enumerate(path.open()):
            if i >= 365:
                raise ValueError('Excess dates')
            row = json.loads(line)
            state, residual, costs = check_day(row, days[i], price, state, True)
            worst = max(worst, residual)
            if row['policy'] != report['policy'] or row['controller'] != mode or row['revisions']:
                raise ValueError('Controller/contract mismatch')
            if mode == 'B0':
                commitments.append(row['planned_G'])
            elif not np.array_equal(commitments[i], row['planned_G']):
                raise ValueError('B0 and B1 must use identical G')
            start = midnight(days[i].day)
            commands = row['commands']
            if len(commands) != 144:
                raise ValueError('Missing commands')
            for j, command in enumerate(commands):
                decision = start+timedelta(minutes=10*j)
                block = start+timedelta(minutes=10*(j-j % 6)) if mode == 'B1' else decision
                latest = (start+timedelta(minutes=10*j)).isoformat() if j else None
                if (command['slot'] != j or command['decision_time'] != decision.isoformat() or
                    command['block_decision_time'] != block.isoformat() or
                    command['latest_observation_end'] != latest or
                    datetime.fromisoformat(command['forecast_available_at']) > block or
                    command['C'] != row['schedule']['C'][j] or command['D'] != row['schedule']['D'][j]):
                    raise ValueError('Command chronology or actual schedule mismatch')
            if [s['slot'] for s in row['solves']] != (list(range(0,144,6)) if mode == 'B1' else []):
                raise ValueError('Replan frequency mismatch')
            if i < 31:
                warmup += costs['total_yuan']
            else:
                forecast_load = days_by_date[row['forecast_sources']['load']['source_day']].load_kwh
                forecast_pv = days_by_date[row['forecast_sources']['pv']['source_day']].pv_kwh
                s = {k: np.asarray(v) for k, v in row['schedule'].items()}
                predicted_u = np.maximum(forecast_load+s['C']-s['G']-forecast_pv-s['D'], 0.)
                predicted_emergency += float(predicted_u.sum())
                predicted_emergency_slots += int((predicted_u > 1e-6).sum())
                for k, v in costs.items():
                    totals[k] += v
                month = row['day'][:7]
                months[month] = months.get(month, 0.)+costs['total_yuan']
            count += 1
        if count != 365 or abs(warmup-expected['warmup_cost_yuan']) > 1e-5:
            raise ValueError('Warmup coverage/fee mismatch')
        if any(abs(totals[k]-expected['costs'][k]) > 1e-5 for k in totals) or months != expected['monthly_total_yuan']:
            raise ValueError('Evaluation summary mismatch')
        evidence[mode] = {'days_verified': count, 'slots_verified': count*144,
            'evaluation_days': 334, 'max_physical_residual_kwh': worst, 'costs': totals,
            'frozen_forecast_emergency_kwh': predicted_emergency,
            'frozen_forecast_emergency_slots_above_tolerance': predicted_emergency_slots,
            'chronology_checked': True, 'passed': True}
    dump(OUT/'independent_validation.json', {'passed': True, 'strategies': evidence,
        'paired_commitments_identical': True,
        'information_boundary_evidence': 'timestamp audit plus tests/test_strict_execution.py perturbation tests; metadata alone does not prove causality',
        'result_sha256': hashlib.sha256((OUT/'result.json').read_bytes()).hexdigest(),
        'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    print('Independent validation passed: 730 day traces, 105120 slots, identical paired commitments')


if __name__ == '__main__':
    verify()
