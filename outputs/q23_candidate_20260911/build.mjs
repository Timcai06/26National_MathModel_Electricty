import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const builderDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(builderDir, '../..');
const q4 = process.argv.includes('--q4');
const out = q4 ? path.join(root, 'outputs/q4_candidate_20260911') : builderDir;
const preview = process.argv.includes('--preview');
const readback = process.argv.includes('--readback');
for (const number of [2, 3]) {
  if (process.argv.includes('--focus-adjust') && number === 2) continue;
  const identifier = q4 ? `4-${number}` : `${number}`;
  const template = path.join(root, `CUMCM2026Problems/C题/附件/附件5/result${identifier}.xlsx`);
  const output = path.join(out, `result${identifier}_candidate.xlsx`);
  const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(readback ? output : template));
  if (!preview && !readback) {
    const payload = JSON.parse(await fs.readFile(path.join(out, `payload${identifier}.json`), 'utf8'));
    if (createHash('sha256').update(await fs.readFile(template)).digest('hex') !== payload.template_sha256) throw new Error('Template changed');
    for (const [name, table] of Object.entries(payload.sheets)) {
      const ws = wb.worksheets.getItem(name);
      if (name === '充放电量') {
        // Expand the template's six-row daily block, replacing illustrative ellipses.
        for (let d = 1; d < 334; d++) ws.getRangeByIndexes(1+d*6, 0, 6, 6).copyFrom(ws.getRange('A2:F7'), 'all');
      } else if (name === '紧急购电量') {
        for (let r = 2; r < table.values.length+1; r++) ws.getRangeByIndexes(r, 0, 1, 3).copyFrom(ws.getRange('A3:C3'), 'all');
      }
      const values = table.values.map(row => row.map((value, col) => col === 0 && table.dates && value !== null ? new Date(`${value}T00:00:00Z`) : value));
      ws.getRangeByIndexes(1, table.start_column, values.length, values[0].length).values = values;
    }
    wb.recalculate();
    console.log((await wb.inspect({kind:'match', searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!', options:{useRegex:true,maxResults:10}, maxChars:1000})).ndjson);
    await (await SpreadsheetFile.exportXlsx(wb)).save(output);
    console.log('Exported', output);
  }
  if (process.argv.includes('--focus-adjust')) console.log((await wb.inspect({kind:'table', range:'调整购电量!A1:F6', include:'values', tableMaxRows:6, tableMaxCols:6})).ndjson);
  const names = process.argv.includes('--focus-adjust') ? ['调整购电量'] : ['计划购电量', ...(number === 3 ? ['调整购电量'] : []), '充放电量', '紧急购电量'];
  for (const [index, name] of names.entries()) {
    const range = process.argv.includes('--focus-adjust') ? 'AJ1:AO8' : name === '充放电量' ? 'A1:F13' : name === '紧急购电量' ? 'A1:C12' : 'A1:F6';
    const image = await wb.render({sheetName:name, range, scale:1.5, format:'png'});
    await fs.writeFile(path.join(out, `${preview ? 'template' : readback ? 'final' : 'candidate'}${number}_${process.argv.includes('--focus-adjust') ? 'adjust_focus' : index}.png`), new Uint8Array(await image.arrayBuffer()));
  }
  if (readback) {
    for (const [label, name, range] of [['end', '计划购电量', 'EM331:EQ335'], ['battery_end', '充放电量', 'A2000:F2005']]) {
      const image = await wb.render({sheetName:name, range, scale:1.5, format:'png'});
      await fs.writeFile(path.join(out, `final${number}_${label}.png`), new Uint8Array(await image.arrayBuffer()));
    }
  }
}
