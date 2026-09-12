"""Q1 candidate cell contract and independent readback; no XLSX authoring."""
from datetime import date, datetime
from copy import copy
import hashlib
import math
import re
from pathlib import Path
import os
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import openpyxl

from src.core import BatteryParams
from src.time_axis import time_semantics_attestation
from src.core.solver import SolveResult
from .solve import prepare_q1_inputs
from .tables import TableTimeContract, extract_q1_tables

SHEETS = ['计划购电量', '充放电量']
OUTPUT_POLICY = 'interval-end-v1'
NS = {'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def preserve_template_package(candidate, template, payload):
    """Retain template metadata unsupported by artifact export.

    Numerical cells must already have been authored by the spreadsheet engine.
    Only their numeric value nodes are transplanted into the original package.
    """
    verify_candidate(candidate, template, payload)
    if Path(candidate).resolve() == Path(template).resolve():
        raise ValueError('Cannot overwrite original template')
    with ZipFile(template) as original, ZipFile(candidate) as generated:
        replacements = {}
        for index, name in enumerate(SHEETS, 1):
            part = f'xl/worksheets/sheet{index}.xml'
            source_xml = original.read(part).decode('utf-8')
            dst = ET.fromstring(generated.read(part))
            authored = {c.attrib['r']: c for c in dst.findall('.//s:sheetData/s:row/s:c', NS)}
            for address in payload['cells'][name]:
                numeric = authored[address]
                if numeric.attrib.get('t', 'n') != 'n' or numeric.find('s:v', NS) is None:
                    raise ValueError('Expected engine-authored numeric cell')
                value = numeric.find('s:v', NS).text
                pattern = rf'<c\b[^>]*\br="{address}"[^>]*?(?:/>|>.*?</c>)'
                match = re.search(pattern, source_xml)
                if match:
                    # Original target is empty. Keep every original cell attribute.
                    if not match.group().endswith('/>'):
                        raise ValueError('Expected an empty target cell XML node')
                    replacement = match.group()[:-2] + f'><v>{value}</v></c>'
                    source_xml = source_xml[:match.start()] + replacement + source_xml[match.end():]
                else:
                    row_id = re.search(r'\d+', address).group()
                    row_pattern = rf'(<row\b[^>]*\br="{row_id}"[^>]*>)(.*?)(</row>)'
                    row = re.search(row_pattern, source_xml)
                    if row is None:
                        raise ValueError('Missing template row')
                    content = row.group(2)
                    later = next((c for c in re.finditer(r'<c\b[^>]*\br="([A-Z]+)\d+"', content)
                                  if c.group(1) > re.match(r'[A-Z]+', address).group()), None)
                    position = later.start() if later else len(content)
                    content = content[:position] + f'<c r="{address}"><v>{value}</v></c>' + content[position:]
                    source_xml = source_xml[:row.start(2)] + content + source_xml[row.end(2):]
            replacements[part] = source_xml.encode('utf-8')
        descriptor, temporary = tempfile.mkstemp(suffix='.xlsx', dir=Path(candidate).parent)
        os.close(descriptor)
        try:
            with ZipFile(temporary, 'w') as final:
                for entry in original.infolist():
                    final.writestr(entry, replacements.get(entry.filename, original.read(entry.filename)))
            os.replace(temporary, candidate)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_payload(report, template, *, output_policy, allow_real_candidate=False):
    """Explicit synthetic positional experiment, never a production mapping."""
    if output_policy != OUTPUT_POLICY:
        raise ValueError('Explicit candidate positional policy required')
    inputs = dict(report['input'])
    real_candidate = allow_real_candidate and inputs['input_metadata']['input_kind'] == 'standardized'
    if inputs['input_metadata']['input_kind'] != 'synthetic' and not real_candidate:
        raise ValueError('Only synthetic candidates are supported until mapping acceptance')
    inputs['battery_params'] = BatteryParams(**inputs['battery_params'])
    model, price, metadata = prepare_q1_inputs(**inputs)
    result = SolveResult(**report['comparison']['strategies']['optimized'])
    if any(result.metadata.get(k) != v for k, v in metadata.items()):
        raise ValueError('Input and result provenance mismatch')
    recorded = report['tables']['optimized']
    contract = TableTimeContract(date.fromisoformat(recorded['day']),
        tuple(datetime.fromisoformat(b) for b in recorded['physical_boundaries']),
        recorded['metadata']['mapping_version'], recorded['time_contract_status'])
    table = extract_q1_tables(result, model=model, price_yuan_per_kwh=price,
                             time_contract=contract, strategy='optimized', allow_candidate_time=real_candidate)
    for key in ('table1', 'table2', 'daily_totals', 'metadata', 'physical_boundaries'):
        if table[key] != recorded[key]:
            raise ValueError('Table and schedule mismatch: ' + key)
    wb = openpyxl.load_workbook(template)
    if wb.sheetnames != SHEETS or [(s.max_row, s.max_column) for s in wb] != [(145, 2), (7, 5)]:
        raise ValueError('Unexpected Q1 template structure')
    if [wb[SHEETS[0]][c].value for c in ['A1','B1','A2','A145']] != ['时间段','购电量','0:10-0:20','0:00+1-0:10+1']:
        raise ValueError('Unexpected purchase template labels')
    if list(next(wb[SHEETS[1]].values)) != ['时间段','充电量','放电量','时刻','储电量']:
        raise ValueError('Unexpected battery headers')
    for i in range(6):
        if wb[SHEETS[1]][f'A{i+2}'].value != f'{4*i}:00-{4*i+4}:00':
            raise ValueError('Unexpected four-hour labels')
    if [wb[SHEETS[1]][c].value for c in ['D2','D3']] != ['0:00','24:00']:
        raise ValueError('Unexpected state boundary labels')
    # Verify all official purchase labels, not merely first and last.
    def label(minutes):
        day, minute = divmod(minutes, 1440)
        hour, minute = divmod(minute, 60)
        return f'{hour}:{minute:02d}' + ('+1' if day else '')
    for i in range(144):
        if wb[SHEETS[0]][f'A{i+2}'].value != f'{label((i+1)*10)}-{label((i+2)*10)}':
            raise ValueError('Unexpected purchase label at slot ' + str(i))
    cells = {SHEETS[0]: {f'B{i+2}': float(g) for i, g in enumerate(result.schedule['G'])}, SHEETS[1]: {}}
    for i, row in enumerate(table['table2'], 2):
        cells[SHEETS[1]].update({f'B{i}': row['charge_bus_kwh'], f'C{i}': row['discharge_bus_kwh']})
    cells[SHEETS[1]].update(E2=table['daily_totals']['initial_energy_kwh'], E3=table['daily_totals']['terminal_energy_kwh'])
    for sheet, patch in cells.items():
        if any(wb[sheet][cell].value is not None for cell in patch):
            raise ValueError('Expected a blank official template, not an existing result')
    mapping = [{'slot_id': i, 'cell': f'B{i+2}', 'template_label': wb[SHEETS[0]][f'A{i+2}'].value,
                'physical_start': contract.boundaries[i].isoformat(), 'physical_end': contract.boundaries[i+1].isoformat(),
                'label_offset_minutes': 10} for i in range(144)]
    wb.close()
    return {'scope':'real-candidate-only' if real_candidate else 'synthetic-candidate-only', 'output_policy':output_policy,
            'semantic_acceptance':False, 'time_semantics':time_semantics_attestation(), 'template_sha256':sha256(template),
            'cells':cells, 'mapping':mapping, 'table':table}


def verify_candidate(candidate, template, payload):
    """Reopen saved XLSX; check all target values and all unrelated cells."""
    if sha256(template) != payload['template_sha256']:
        raise ValueError('Original template changed')
    source = openpyxl.load_workbook(template)
    actual = openpyxl.load_workbook(candidate)
    if actual.sheetnames != source.sheetnames:
        raise ValueError('Sheet names/order changed')
    count, style_changes = 0, []
    for name in source.sheetnames:
        a, b = source[name], actual[name]
        if (a.max_row, a.max_column) != (b.max_row, b.max_column):
            raise ValueError('Sheet dimensions changed')
        if list(a.merged_cells.ranges) != list(b.merged_cells.ranges):
            raise ValueError('Merged ranges changed')
        for row in a:
            for old in row:
                new = b[old.coordinate]
                if old.coordinate in payload['cells'][name]:
                    expected = payload['cells'][name][old.coordinate]
                    if (isinstance(new.value, bool) or not isinstance(new.value, (int,float))
                            or not math.isfinite(new.value) or abs(new.value-expected) >= 1e-6):
                        raise ValueError(f'Numeric readback mismatch: {name}!{old.coordinate}')
                    count += 1
                elif new.value != old.value or new.data_type != old.data_type:
                    # Some engines serialize empty inline strings as empty numeric cells.
                    if not (new.value is None and old.value is None):
                        raise ValueError(f'Unrelated cell changed: {name}!{old.coordinate}')
                if (copy(old.font) != copy(new.font) or copy(old.fill) != copy(new.fill) or copy(old.border) != copy(new.border)
                        or copy(old.alignment) != copy(new.alignment) or old.number_format != new.number_format
                        or copy(old.protection) != copy(new.protection)):
                    style_changes.append(f'{name}!{old.coordinate}')
    purchase = [actual[SHEETS[0]][f'B{i+2}'].value for i in range(144)]
    totals = payload['table']['daily_totals']
    if abs(sum(purchase)-totals['purchase_kwh']) >= 1e-6:
        raise ValueError('Daily purchase sum mismatch')
    for column, key in [('B','charge_bus_kwh'),('C','discharge_bus_kwh')]:
        if abs(sum(actual[SHEETS[1]][f'{column}{i}'].value for i in range(2,8))-totals[key]) >= 1e-6:
            raise ValueError('Four-hour energy sum mismatch')
    source.close()
    actual.close()
    with ZipFile(template) as a, ZipFile(candidate) as b:
        unchanged_parts = (set(a.namelist()) == set(b.namelist()) and all(
            a.read(name) == b.read(name) for name in a.namelist()
            if name not in ['xl/worksheets/sheet1.xml','xl/worksheets/sheet2.xml']))
    return {'numeric_readback_passed':True, 'cells_verified':count,
            'template_unchanged':True, 'unrelated_values_unchanged':True,
            'style_changes':style_changes, 'nonworksheet_package_preserved':unchanged_parts,
            'semantic_acceptance':False, 'time_semantics':time_semantics_attestation(),
            'candidate_sha256':sha256(candidate)}
