"""Prepare or verify the explicit synthetic Q1 template experiment."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.q1.excel import OUTPUT_POLICY, candidate_payload, verify_candidate, preserve_template_package


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'finalize', 'verify'])
    parser.add_argument('--real', action='store_true', help='Explicit real-data candidate; not final submission')
    args = parser.parse_args()
    output = ROOT / 'outputs/q1_candidate_20260911'
    if args.real:
        output = ROOT / 'outputs/q1_real_candidate_20260911'
    filename = 'result1_candidate.xlsx' if args.real else 'result1_synthetic_candidate.xlsx'
    template = ROOT / 'CUMCM2026Problems/C题/附件/附件5/result1.xlsx'
    source = ROOT / 'analysis/q1_tables/tables.json'
    if args.real:
        source = ROOT / 'analysis/real_q1_candidate/result.json'
    bundle = json.loads(source.read_text())
    if args.real:
        csv_source = ROOT / bundle['source']
        if hashlib.sha256(csv_source.read_bytes()).hexdigest() != bundle['source_sha256']:
            raise ValueError('Real source changed since solve')
    result = bundle['report'] if args.real else bundle['reports']['seeded_variable_day']
    payload = candidate_payload(result, template, output_policy=OUTPUT_POLICY, allow_real_candidate=args.real)
    payload['source_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    payload['case'] = 'attachment1_real_candidate' if args.real else 'seeded_variable_day'
    if args.action == 'prepare':
        output.mkdir(parents=True, exist_ok=True)
        (output / 'payload.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n')
        with (output / 'slot_mapping.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(payload['mapping'][0]));writer.writeheader();writer.writerows(payload['mapping'])
        print('Prepared 158 cells;', payload['scope'], '; semantic acceptance FALSE')
    else:
        saved = json.loads((output / 'payload.json').read_text())
        if saved != payload:
            raise ValueError('Payload stale or changed since source validation')
        if args.action == 'finalize':
            preserve_template_package(output / filename, template, payload)
        report = verify_candidate(output / filename, template, payload)
        report['source_sha256'] = payload['source_sha256']
        report['code_sha256'] = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__).resolve(), ROOT/'src/q1/excel.py', ROOT/'outputs/q1_candidate_20260911/build_candidate.mjs']}
        (output / 'readback.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps(report, ensure_ascii=False))
        if report['style_changes'] or not report['nonworksheet_package_preserved']:
            raise ValueError('Template style preservation failed')


if __name__ == '__main__':
    main()
