import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, readdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { createServer } from '../frontend/node_modules/vite/dist/node/index.js';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const { values } = parseArgs({ options: {
  physics: { type: 'string' }, watersheds: { type: 'string' }, report: { type: 'string' },
} });
assert(values.physics && values.watersheds && values.report);
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
  const { physicsDto } = await server.ssrLoadModule('/src/domains/physics/dto/physicsDto.ts');
  const { watershedJobDto } = await server.ssrLoadModule('/src/domains/watershed/dto/watershedDto.ts');
  const { lifeCycleCostDto } = await server.ssrLoadModule('/src/domains/cost/dto/lifeCycleCostDto.ts');
  const physics = await source(path.resolve(values.physics));
  physicsDto.parse(physics);
  assert.equal(physics.result.lifeCycleCost.status, 'UNAVAILABLE');
  const changed = structuredClone(physics);
  changed.result.lifeCycleCost.planSha256 = '0'.repeat(64);
  assert(!physicsDto.safeParse(changed).success);
  let jobs = 0, quotes = 0;
  for (const filename of (await readdir(values.watersheds)).filter(n => /^api-view-.*\.json$/.test(n))) {
    const job = await source(path.resolve(values.watersheds, filename));
    watershedJobDto.parse(job);
    jobs++;
    for (const item of job.result.cisternLifeCycleCosts.items) {
      for (const quote of item.quotes) {
        const report = quote.report;
        assert.equal(report.status, 'PARTIAL');
        assert.equal(report.lifeCycleCost, null);
        assert(report.knownPresentValue !== null);
        const ledger = structuredClone(report);
        ledger.annualCashflows[0].presentValue = '0.00';
        assert(!lifeCycleCostDto.safeParse(ledger).success);
        const complete = { ...report, status: 'COMPLETE' };
        assert(!lifeCycleCostDto.safeParse(complete).success);
        quotes++;
      }
    }
  }
  assert(jobs >= 2 && quotes >= 3);
  const report = {
    status: 'PASS', weeklyResponses: 1, watershedResponses: jobs, partialQuotes: quotes,
    apiDtoMatched: true, changedPlanRejected: true, changedLedgerRejected: true,
    incompleteFullCostRejected: true, sourceHashes: hashes,
    scope: '실제 격리 API·워커 결과의 화면 DTO 검사; 브라우저 표시 검증과 구분',
  };
  await writeFile(values.report, JSON.stringify(report, null, 2) + '\n', { flag: 'wx' });
  console.log(JSON.stringify(report));
} finally {
  await server.close();
}
