import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { gunzipSync } from 'node:zlib';
import { createServer } from '../frontend/node_modules/vite/dist/node/index.js';
const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const { values } = parseArgs({ options: { report: { type: 'string' } } });
assert(values.report);
const hash = raw => createHash('sha256').update(raw).digest('hex');
const base = path.join(root, 'frontend/public/data');
const indexRaw = await readFile(path.join(base, 'seoul-candidates-v1/index.json'));
const index = JSON.parse(indexRaw);
const info = JSON.parse(await readFile(path.join(base, 'seoul-terrain-native-v1/terrain.json')));
const files = {};
for (const [name, entry] of Object.entries(info.files)) {
  const raw = await readFile(path.join(base, 'seoul-terrain-native-v1', name));
  assert.equal(hash(raw), entry.sha256);
  files[name] = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
}
const terrain = { ...info, heights: new Float32Array(files['height-f32le.bin']),
  districts: new Uint8Array(files['district-u8.bin']), cover: new Uint8Array(files['cover-u8.bin']) };
const server = await createServer({ root: path.join(root, 'frontend'), server: { middlewareMode: true }, appType: 'custom' });
try {
  const { candidateDisplayRowsDto } = await server.ssrLoadModule('/src/domains/installation/repository/candidateDisplayRepository.ts');
  const { candidateGeometry } = await server.ssrLoadModule('/src/domains/installation/service/candidateGeometryService.ts');
  const { terrainMeshHeight } = await server.ssrLoadModule('/src/domains/terrain/service/terrainDrapeService.ts');
  const largest = new Set([...index.tiles].sort((a,b) => b.bytes-a.bytes).slice(0,3).map(t => t.id));
  const stress = [];
  let records = 0;
  for (const entry of index.tiles) {
    const raw = gunzipSync(await readFile(path.join(base, 'seoul-candidates-v1', entry.file)), { maxOutputLength: entry.bytes });
    assert.equal(hash(raw), entry.sha256);
    const rows = candidateDisplayRowsDto.parse(JSON.parse(raw));
    assert.equal(rows.length, entry.count);
    records += rows.length;
    if (!largest.has(entry.id)) continue;
    const started = performance.now(), mesh = candidateGeometry(rows, terrain);
    const geometryMs = performance.now() - started;
    assert.equal(mesh.ends.length, rows.length);
    for (const value of [mesh.positions, mesh.masks, mesh.bounds]) assert(value.every(Number.isFinite));
    for (let i=0; i<mesh.positions.length; i+=3) {
      const expected = terrainMeshHeight(terrain, [mesh.positions[i], -mesh.positions[i+2]]) + .18;
      assert(Math.abs(mesh.positions[i+1]-expected) < .002);
    }
    stress.push({id:entry.id, candidates:rows.length, vertices:mesh.positions.length/3, geometryMs,
      bufferBytes:mesh.positions.byteLength+mesh.masks.byteLength+mesh.bounds.byteLength});
  }
  const report = { schemaVersion:1, status:'PASS', indexSha256:hash(indexRaw), tiles:index.tiles.length,
    records, allTileDtoValidated:true, terrainHeightsChecked:true, stress,
    scope:'실제 후보 타일·지형의 CPU 형상 검사. 브라우저 FPS 측정과 구분' };
  await writeFile(path.resolve(values.report), JSON.stringify(report)+'\n', {flag:'wx'});
  console.log(JSON.stringify(report));
} finally { await server.close(); }
