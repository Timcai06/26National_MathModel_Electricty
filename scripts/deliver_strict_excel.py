"""Write the five official result workbooks from the current verified strategies.

Pure Python: the official template is opened, filled and saved under outputs/.
Original files are never modified. Every written cell is read back from the saved
workbook and compared against the source trajectory before the run is accepted.
"""
import csv
import hashlib
import json
import shutil
import sys
from copy import copy
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import openpyxl
from openpyxl.utils import get_column_letter

from src.q3.reporting import emergency_intervals, time_label
from src.time_axis import time_semantics_attestation

TEMPLATES = ROOT / 'CUMCM2026Problems/C题/附件/附件5'
OUT = ROOT / 'deliverables/final_submission/excel'
BUCKETS = [f'{4 * b}:00-{4 * b + 4}:00' for b in range(6)]

# Which verified trajectory backs each official workbook.
SOURCES = {
    '2': {'trace': 'analysis/q2_margin_oracle_v1/B2.jsonl',
          'result': 'analysis/q2_margin_oracle_v1/result.json', 'key': ('strategies', 'B2'),
          'strategy': 'B2 安全裕量，零点固定合同', 'adjusted': False},
    '3': {'trace': 'analysis/strict_q3_transfer_v1/margin_zero.jsonl',
          'result': 'analysis/strict_q3_transfer_v1/result.json', 'key': ('strategies', 'margin_zero'),
          'strategy': '裕量零点固定（第三问主候选）', 'adjusted': True},
    '4-2': {'trace': 'analysis/strict_q4_transfer_v1/q4-2_B2.jsonl',
            'result': 'analysis/strict_q4_transfer_v1/result.json', 'key': ('q4-2', 'B2'),
            'strategy': '动态电价下的B2安全裕量', 'adjusted': False},
    '4-3': {'trace': 'analysis/strict_q4_transfer_v1/q4-3_margin_zero.jsonl',
            'result': 'analysis/strict_q4_transfer_v1/result.json', 'key': ('q4-3', 'margin_zero'),
            'strategy': '动态电价下的裕量零点固定', 'adjusted': True},
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dig(obj, keys):
    for key in keys:
        obj = obj[key]
    return obj


def load_trace(spec):
    """Refuse any trajectory whose bound independent validation is missing or stale."""
    result_path = ROOT / spec['result']
    report = json.loads(result_path.read_text())
    validation_path = result_path.with_name('independent_validation.json')
    validation = json.loads(validation_path.read_text())
    if not validation['passed'] or validation['result_sha256'] != sha(result_path):
        raise ValueError(f'{spec["result"]}: independent validation missing or stale')
    entry = dig(report, spec['key'])
    trace = ROOT / spec['trace']
    if sha(trace) != entry['daily_file_sha256']:
        raise ValueError(f'{spec["trace"]}: trajectory changed since the validated run')
    rows = [json.loads(line) for line in trace.read_text().splitlines()]
    if len(rows) != 334:
        raise ValueError(f'{spec["trace"]}: expected 334 evaluation days')
    return rows, entry


def style_from(worksheet, row, column):
    return copy(worksheet.cell(row, column)._style)


def fill_daily_axis(ws, rows, values_of, totals_of):
    """One row per date: 144 slot values, then the day's total energy and fee."""
    written = {}
    for index, row in enumerate(rows):
        excel_row = index + 2
        day = date(2025, 2, 1) + timedelta(days=index)
        stamp = ws.cell(excel_row, 1).value
        if row['day'] != str(day) or stamp.date() != day:
            raise ValueError('Template date does not match the trajectory')
        values = values_of(row)
        if len(values) != 144:
            raise ValueError('Expected 144 slot values')
        for slot, value in enumerate(values):
            ws.cell(excel_row, slot + 2, float(value))
            written[f'{get_column_letter(slot + 2)}{excel_row}'] = float(value)
        for offset, value in enumerate(totals_of(row)):
            ws.cell(excel_row, 146 + offset, float(value))
            written[f'{get_column_letter(146 + offset)}{excel_row}'] = float(value)
    return written


def fill_battery(ws, rows):
    """Expand the six-row illustrative block to 334 days without losing styles."""
    block_styles = [[style_from(ws, 2 + b, c) for c in range(1, 7)] for b in range(6)]
    zero_label, end_label = ws.cell(2, 5).value, ws.cell(3, 5).value
    for excel_row in range(ws.max_row, 1, -1):
        ws.delete_rows(excel_row)
    written = {}
    for index, row in enumerate(rows):
        day = date(2025, 2, 1) + timedelta(days=index)
        schedule = row['schedule']
        for b in range(6):
            excel_row = 2 + index * 6 + b
            lo, hi = b * 24, (b + 1) * 24
            cells = [datetime.combine(day, time.min) if b == 0 else None, BUCKETS[b],
                     float(sum(schedule['C'][lo:hi])), float(sum(schedule['D'][lo:hi])),
                     zero_label if b == 0 else end_label if b == 1 else None,
                     float(schedule['E'][0]) if b == 0 else float(schedule['E'][-1]) if b == 1 else None]
            for c, value in enumerate(cells, 1):
                cell = ws.cell(excel_row, c, value)
                cell._style = copy(block_styles[b][c - 1])
                if value is not None:
                    written[f'{get_column_letter(c)}{excel_row}'] = value
    return written


def fill_emergency(ws, rows):
    """One row per contiguous emergency interval; days without any are written 无."""
    first_style = [style_from(ws, 2, c) for c in range(1, 4)]
    later_style = [style_from(ws, 3, c) for c in range(1, 4)]
    for excel_row in range(ws.max_row, 1, -1):
        ws.delete_rows(excel_row)
    written, excel_row = {}, 2
    for index, row in enumerate(rows):
        day = date(2025, 2, 1) + timedelta(days=index)
        intervals = emergency_intervals(row['schedule']['U'])
        entries = ([(interval['interval'], interval['purchase_kwh']) for interval in intervals]
                   or [('无', 0.0)])
        for k, (label, amount) in enumerate(entries):
            cells = [datetime.combine(day, time.min) if k == 0 else None, label, float(amount)]
            styles = first_style if k == 0 else later_style
            for c, value in enumerate(cells, 1):
                cell = ws.cell(excel_row, c, value)
                cell._style = copy(styles[c - 1])
                if value is not None:
                    written[f'{get_column_letter(c)}{excel_row}'] = value
            excel_row += 1
    return written


def build(identifier, spec):
    rows, entry = load_trace(spec)
    template = TEMPLATES / f'result{identifier}.xlsx'
    template_hash = sha(template)
    target = OUT / f'result{identifier}.xlsx'
    wb = openpyxl.load_workbook(template)
    written = {}

    plan_written = fill_daily_axis(
        wb['计划购电量'], rows,
        values_of=lambda r: r['planned_G'],
        totals_of=lambda r: (sum(r['planned_G']),
                             r['costs']['total_yuan'] if not spec['adjusted'] else r['costs']['planned_yuan']))
    written['计划购电量'] = plan_written
    if spec['adjusted']:
        written['调整购电量'] = fill_daily_axis(
            wb['调整购电量'], rows,
            values_of=lambda r: r['schedule']['G'],
            totals_of=lambda r: (sum(r['schedule']['G']), r['costs']['total_yuan']))
    written['充放电量'] = fill_battery(wb['充放电量'], rows)
    written['紧急购电量'] = fill_emergency(wb['紧急购电量'], rows)

    OUT.mkdir(parents=True, exist_ok=True)
    wb.save(target)
    wb.close()
    if sha(template) != template_hash:
        raise ValueError('Official template changed during authoring')
    return target, rows, entry, written, template_hash


def verify(target, written):
    """Reopen the saved workbook and compare every authored cell."""
    wb = openpyxl.load_workbook(target, data_only=True)
    count = 0
    for sheet, cells in written.items():
        ws = wb[sheet]
        for address, expected in cells.items():
            actual = ws[address].value
            if isinstance(expected, float):
                if not isinstance(actual, (int, float)) or abs(actual - expected) > 1e-9:
                    raise ValueError(f'{target.name}/{sheet}!{address}: {actual!r} != {expected!r}')
            elif isinstance(expected, datetime):
                if actual != expected:
                    raise ValueError(f'{target.name}/{sheet}!{address}: {actual!r} != {expected!r}')
            elif actual != expected:
                raise ValueError(f'{target.name}/{sheet}!{address}: {actual!r} != {expected!r}')
            count += 1
    wb.close()
    return count


def main():
    manifest = {'scope': 'official result workbooks written from the current verified strategies',
                'time_semantics': time_semantics_attestation(),
                'label_offset_note': ('values are filled positionally; the printed purchase-axis label of a '
                                      'column reads ten minutes later than its physical interval'),
                'files': {}}
    total_cells = 0
    for identifier, spec in SOURCES.items():
        target, rows, entry, written, template_hash = build(identifier, spec)
        count = verify(target, written)
        total_cells += count
        manifest['files'][f'result{identifier}.xlsx'] = {
            'strategy': spec['strategy'], 'source_trace': spec['trace'],
            'source_trace_sha256': sha(ROOT / spec['trace']),
            'template_sha256': template_hash, 'candidate_sha256': sha(target),
            'days': len(rows), 'cells_written_and_read_back': count,
            'annual_total_yuan': entry['costs']['total_yuan'],
            'annual_emergency_yuan': entry['costs']['emergency_yuan'],
            'annual_emergency_kwh': entry['emergency_kwh']}
        print(f'result{identifier}.xlsx  {count:>7,} cells verified  '
              f"总费 {entry['costs']['total_yuan']:>16,.2f} 元", flush=True)

    # Question 1 is a single representative day and keeps its own audited pipeline.
    q1_source = ROOT / 'outputs/q1_real_candidate_20260911/result1_candidate.xlsx'
    q1_readback = json.loads((q1_source.parent / 'readback.json').read_text())
    if not q1_readback['numeric_readback_passed'] or q1_readback['candidate_sha256'] != sha(q1_source):
        raise ValueError('Q1 candidate workbook lacks a current readback')
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(q1_source, OUT / 'result1.xlsx')
    manifest['files']['result1.xlsx'] = {
        'strategy': '代表日优化调度', 'source': str(q1_source.relative_to(ROOT)),
        'template_sha256': q1_readback.get('template_sha256'), 'candidate_sha256': sha(OUT / 'result1.xlsx'),
        'days': 1, 'cells_written_and_read_back': q1_readback['cells_verified']}
    total_cells += q1_readback['cells_verified']
    print(f"result1.xlsx      {q1_readback['cells_verified']:>7,} cells verified (existing audited pipeline)")

    manifest['total_cells_verified'] = total_cells
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with (OUT / 'summary.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['file', 'strategy', 'days', 'cells_verified', 'annual_total_yuan'])
        for name, entry in manifest['files'].items():
            writer.writerow([name, entry['strategy'], entry['days'],
                             entry['cells_written_and_read_back'], entry.get('annual_total_yuan', '')])
    print(f'\n{total_cells:,} cells written and read back; manifest in {OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
