"""Reproduce the paper's representative-day optimum without plotting."""
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.model import BatteryParams
from src.q1.solve import solve_q1


def main():
    source = ROOT / 'data/processed/team_delivery/day_base.csv'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    audit = json.loads((ROOT / 'analysis/team_delivery/intake_audit.json').read_text())
    if audit['input_sha256'][str(source.relative_to(ROOT))] != digest:
        raise ValueError('Representative-day data differ from the audited input')
    with source.open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle))
    result = solve_q1(
        load_kwh=[float(r['load_kwh']) for r in rows],
        pv_forecast_kwh=[float(r['pv_forecast_kwh']) for r in rows],
        price_yuan_per_kwh=[float(r['price']) for r in rows],
        slot_ids=[int(r['slot']) for r in rows],
        initial_energy_kwh=6000, battery_params=BatteryParams(.9, .9, 'bus'),
        input_metadata={'input_kind': 'standardized', 'data_version': digest,
                        'mapping_version': 'interval-end-v1',
                        'assumptions_version': 'eta0.9-each-bus-neutral6000'},
    )
    if result.status != 'optimal' or not result.diagnostics['passed']:
        raise RuntimeError(f'No validated optimum: {result.status}')
    if abs(result.objective_yuan - 35126.948589) > 1e-4:
        raise ValueError('Optimum does not reproduce the paper')
    print(json.dumps({'status': result.status, 'cost_yuan': result.objective_yuan,
                      'purchase_kwh': float(sum(result.schedule['G'])),
                      'no_storage_yuan': result.metadata['no_storage_cost_yuan'],
                      'physical_checks': result.diagnostics}, indent=2))


if __name__ == '__main__':
    main()
