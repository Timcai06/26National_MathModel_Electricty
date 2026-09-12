import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const builderDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(builderDir, '../..');
const real = process.argv.includes('--real');
const out = real ? path.join(root, 'outputs/q1_real_candidate_20260911') : builderDir;
const filename = real ? 'result1_candidate.xlsx' : 'result1_synthetic_candidate.xlsx';
const template = path.join(root, 'CUMCM2026Problems/C题/附件/附件5/result1.xlsx');
const readback = process.argv.includes('--readback');
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(readback ? path.join(out,filename) : template));
const previewOnly = process.argv.includes('--preview');
if (!previewOnly && !readback) {
  const payload = JSON.parse(await fs.readFile(path.join(out, 'payload.json'), 'utf8'));
  const hash = createHash('sha256').update(await fs.readFile(template)).digest('hex');
  if (hash !== payload.template_sha256 || payload.scope !== (real ? 'real-candidate-only' : 'synthetic-candidate-only')) {
    throw new Error('Template hash or candidate scope mismatch');
  }
  for (const [sheet, cells] of Object.entries(payload.cells)) {
    const ws = wb.worksheets.getItem(sheet);
    for (const [cell, value] of Object.entries(cells)) {
      if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error('Invalid number');
      ws.getRange(cell).values = [[value]];
    }
  }
  wb.recalculate();
  console.log((await wb.inspect({kind:'table', range:'充放电量!A1:E7', include:'values,formulas', tableMaxRows:7, tableMaxCols:5})).ndjson);
  console.log((await wb.inspect({kind:'match', searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!', options:{useRegex:true,maxResults:20}})).ndjson);
}
const views = process.argv.includes('--focus') ? [['purchase_middle','计划购电量','A52:B60']] : [['purchase','计划购电量','A1:B12'], ['battery','充放电量','A1:E7'], ['purchase_end','计划购电量','A136:B145']];
for (const [name, sheet, range] of views) {
  const blob = await wb.render({sheetName:sheet, range, scale:2, format:'png'});
  await fs.writeFile(path.join(out, `${readback ? 'final' : previewOnly ? 'template' : 'candidate'}_${name}.png`), new Uint8Array(await blob.arrayBuffer()));
}
if (!previewOnly && !readback) {
  const file = await SpreadsheetFile.exportXlsx(wb);
  await file.save(path.join(out, filename));
  console.log('Exported', filename);
}
