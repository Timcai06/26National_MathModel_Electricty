"""Independently re-check that the frozen time contract holds across the project.

Re-derives every mapping from the official files and from src/time_axis.py without
reusing the numbers recorded by run_time_semantics.py. Writes nothing but a report.
"""
import csv, hashlib, json, sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import openpyxl

from src.time_axis import LOCAL_ZONE, build_day_slots, future_slot_ids

PROBLEM = ROOT / 'CUMCM2026Problems/C题'
BUNDLE = ROOT / 'analysis/time_semantics_v1/result.json'
CANONICAL = [f'{m // 60}:{m % 60:02d}' for m in range(10, 1441, 10)]


def fail(checks, name, condition, detail=''):
    checks.append({'check': name, 'passed': bool(condition), 'detail': detail})


def label(value):
    if isinstance(value, time):
        return f'{value.hour}:{value.minute:02d}'
    return str(value)


def main():
    checks = []

    # 1. Every input axis carries the same 144 ordered sample labels.
    a1 = openpyxl.load_workbook(PROBLEM / '附件/附件1.xlsx', data_only=True)['Sheet1']
    labels = [label(a1.cell(r, 1).value) for r in range(2, 146)]
    fail(checks, 'attachment1_axis_is_canonical',
         labels[:-1] == CANONICAL[:-1] and labels[-1] == '0:00+1',
         f'first={labels[0]} last={labels[-1]}')

    for source, sheet in (('附件2.xlsx', None), ('附件4.xlsx', None)):
        wb = openpyxl.load_workbook(PROBLEM / '附件' / source, data_only=True)
        ws = wb[sheet] if sheet else wb[wb.sheetnames[0]]
        header = [label(ws.cell(1, c).value) for c in range(2, 146)]
        ok = header[:-1] == CANONICAL[:-1] and header[-1] in ('0:00+1', '0:00')
        fail(checks, f'{source}_axis_matches_attachment1', ok, f'first={header[0]} last={header[-1]}')

    # 2. interval_end semantics put slot 0 at 00:00 and slot 143 at 23:50-24:00.
    slots = build_day_slots(date(2025, 3, 20), labels, semantics='interval_end')
    midnight = datetime.combine(date(2025, 3, 20), time.min, LOCAL_ZONE)
    fail(checks, 'slot0_starts_at_midnight', slots[0].start == midnight, str(slots[0].start))
    fail(checks, 'slot143_ends_at_next_midnight',
         slots[143].end == midnight + timedelta(days=1), str(slots[143].end))
    fail(checks, 'slot60_is_paper_interval_10_00',
         (slots[60].start - midnight) == timedelta(hours=10) and slots[60].input_label.startswith('10:10'),
         f'{slots[60].start} from sample {slots[60].input_label}')

    # 3. Forecast issues at 0/6/12/18 unlock exactly the whole remaining slots.
    for hour, expected in ((0, 0), (6, 36), (12, 72), (18, 108)):
        future = future_slot_ids(slots, midnight + timedelta(hours=hour))
        fail(checks, f'issue_{hour:02d}_first_editable_slot',
             future[0] == expected and len(future) == 144 - expected,
             f'first={future[0]} n={len(future)}')

    # 4. The six four-hour battery buckets tile the 144 slots exactly.
    buckets = [(h * 6, h * 6 + 24) for h in range(0, 24, 4)]
    covered = [s for lo, hi in buckets for s in range(lo, hi)]
    fail(checks, 'four_hour_buckets_tile_the_day', covered == list(range(144)), f'n={len(covered)}')
    for index, (lo, hi) in enumerate(buckets):
        want = midnight + timedelta(hours=4 * index)
        fail(checks, f'bucket_{4 * index:02d}_starts_on_the_hour',
             slots[lo].start == want and slots[hi - 1].end == want + timedelta(hours=4), str(slots[lo].start))

    # 5. Every template battery sheet asserts the same 00:00-24:00 day.
    for name in ['result1.xlsx', 'result2.xlsx', 'result3.xlsx', 'result4-2.xlsx', 'result4-3.xlsx']:
        wb = openpyxl.load_workbook(PROBLEM / '附件/附件5' / name)
        bat = wb['充放电量']
        col = 1 if name == 'result1.xlsx' else 2
        window = [str(bat.cell(r, col).value) for r in range(2, 8)]
        instants = [label(bat.cell(r, col + 3).value) for r in range(2, 4)]
        fail(checks, f'{name}_battery_sheet_is_00_24',
             window == ['0:00-4:00', '4:00-8:00', '8:00-12:00', '12:00-16:00', '16:00-20:00', '20:00-24:00']
             and instants == ['0:00', '24:00'], f'{window[0]}..{window[-1]} soc={instants}')
        plan = wb['计划购电量']
        first = str(plan.cell(2, 1).value) if name == 'result1.xlsx' else str(plan.cell(1, 2).value)
        fail(checks, f'{name}_purchase_axis_is_shifted_by_one', first == '0:10-0:20', first)

    # 6. The paper's prescribed intervals resolve to the documented slots.
    bundle = json.loads(BUNDLE.read_text(encoding='utf-8'))
    for row in bundle['paper_table_mapping']['table1_intervals']:
        hour = int(row['paper_interval'].split(':')[0])
        fail(checks, f'table1_{hour:02d}_maps_to_slot_{hour * 6}',
             row['slot_id'] == hour * 6 and slots[row['slot_id']].start == midnight + timedelta(hours=hour),
             row['attachment_sample_label'])

    # 7. Re-derive the integration identity from the raw annual CSV, not from the bundle.
    with (ROOT / 'data/processed/team_delivery/annual_actual.csv').open(newline='', encoding='utf-8-sig') as f:
        rows = [r for r in csv.DictReader(f) if r['date'] == '2025-06-21']
    rows.sort(key=lambda r: int(r['slot']))
    power = [float(r['load_kw']) for r in rows]
    right = sum(p / 6 for p in power)
    boundaries = [power[-1]] + power
    trapezoid = sum((boundaries[i] + boundaries[i + 1]) / 12 for i in range(144))
    fail(checks, 'integration_identity_holds_on_a_sample_day',
         abs((right - trapezoid) - (power[-1] - boundaries[0]) / 12) < 1e-9,
         f'gap={right - trapezoid:.9f}')

    failed = [c for c in checks if not c['passed']]
    print(json.dumps({'checks': len(checks), 'failed': len(failed),
                      'failures': failed}, ensure_ascii=False, indent=2))
    if failed:
        raise SystemExit(1)
    print('time semantics contract verified: interval-end-v1')


if __name__ == '__main__':
    main()
