import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { createServer } from '../frontend/node_modules/vite/dist/node/index.js';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const { values } = parseArgs({ options: {
  java: { type: 'string' }, physics: { type: 'string' }, report: { type: 'string' },
} });
assert(values.java && values.physics && values.report);
const hashes = {};
async function source(filename) {
  const raw = await readFile(filename);
  hashes[path.relative(root, filename)] = createHash('sha256').update(raw).digest('hex');
  return JSON.parse(raw);
}
const server = await createServer({
  root: path.join(root, 'frontend'), server: { middlewareMode: true }, appType: 'custom',
});
try {
  const { siteSuitabilityDto } = await server.ssrLoadModule('/src/domains/installation/dto/siteSuitabilityDto.ts');
  const { physicsDto } = await server.ssrLoadModule('/src/domains/physics/dto/physicsDto.ts');
  const cases = await source(path.resolve(values.java));
  assert.equal(Object.keys(cases).length, 9);
  for (const record of Object.values(cases)) siteSuitabilityDto.parse(record);
  const physics = await source(path.resolve(values.physics));
  physicsDto.parse(physics);
  assert.equal(physics.result.designContract.suitability.status, 'UNKNOWN');
  assert.equal(physics.result.designContract.suitability.constructionApproved, false);
  const changed = structuredClone(physics);
  changed.result.designContract.suitability.status = 'PROHIBITED';
  changed.result.designContract.suitability.explorationAllowed = false;
  assert(!physicsDto.safeParse(changed).success);
  const report = {
    status: 'PASS', javaCases: 9, actualWorkerReadback: true,
    restrictedResultRejected: true, sourceHashes: hashes,
    scope: '실제 API·워커 DTO와 시험 전용 경계 판정; 브라우저 검증·현장 안전 확인과 구분',
  };
  await writeFile(values.report, JSON.stringify(report, null, 2) + '\n', { flag: 'wx' });
  console.log(JSON.stringify(report));
} finally {
  await server.close();
}
