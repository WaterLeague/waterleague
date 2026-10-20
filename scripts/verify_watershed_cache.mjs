import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { createServer } from '../frontend/node_modules/vite/dist/node/index.js';

const root = resolve(import.meta.dirname, '..');
const directory = process.argv[2];
assert(directory, '격리 관망 시험의 .fixtures 폴더 필요');
const require = createRequire(`${root}/frontend/package.json`);
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const server = await createServer({
  root: `${root}/frontend`, server: { middlewareMode: true }, appType: 'custom',
});
try {
  const { watershedJobDto } = await server.ssrLoadModule('/src/domains/watershed/dto/watershedDto.ts');
  const { WatershedResult } = await server.ssrLoadModule('/src/domains/watershed/view/WatershedResult.tsx');
  const jobs = new Map();
  const rows = [];
  for (const label of ['S9', 'S1', 'S9-closed', 'S9-pipe', 'S9-narrow', 'S9-reused', 'S9-narrow-reused']) {
    const raw = await readFile(resolve(directory, `api-view-${label}.json`));
    const job = watershedJobDto.parse(JSON.parse(raw));
    const html = renderToStaticMarkup(React.createElement(WatershedResult, { job }));
    assert(job.result.cases.every(c => c.execution?.scope === 'PUBLIC_NETWORK_CASE_V1'));
    const reused = label.endsWith('-reused');
    assert.equal(html.includes('동일 조건의 검증된 계산 결과 재사용'), reused);
    if (reused) {
      const before = jobs.get(label.replace('-reused', ''));
      assert.deepEqual(before.design, job.design);
      const physical = value => {
        const result = structuredClone(value.result);
        for (const c of result.cases) delete c.execution;
        return result;
      };
      assert.deepEqual(physical(before), physical(job));
      assert(job.result.cases.every(c => c.execution.mode === 'REUSED'));
      assert.deepEqual(before.result.cases.map(c => c.execution.computationKey),
        job.result.cases.map(c => c.execution.computationKey));
    }
    const withheld = label.includes('narrow');
    assert.equal(job.result.numericalStatus, withheld ? 'FAILED' : 'PASSED');
    assert.equal(html.includes('월류 시간 효과 비교 보류'), withheld);
    if (withheld) assert.equal(job.result.signedReductionM3, null);
    jobs.set(label, job);
    rows.push({ label, responseSha256: createHash('sha256').update(raw).digest('hex'),
      modes: job.result.cases.map(c => c.execution.mode),
      numericalStatus: job.result.numericalStatus, dtoAndStaticRenderPassed: true });
  }
  await writeFile(`${root}/tmp/watershed-cache-readback-v1.json`,
    JSON.stringify({ schemaVersion: 1, scope: 'HTTP_WORKER_DTO_STATIC_RENDER_NOT_BROWSER', rows }, null, 2) + '\n');
  console.log(JSON.stringify({ status: 'PASSED', responses: rows.length }));
} finally {
  await server.close();
}
