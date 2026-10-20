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
  const rows = [];
  for (const scenario of ['S9', 'S1', 'S9-closed', 'S9-pipe', 'S9-narrow']) {
    const source = resolve(directory, `api-view-${scenario}.json`);
    const raw = await readFile(source);
    const job = watershedJobDto.parse(JSON.parse(raw));
    const html = renderToStaticMarkup(React.createElement(WatershedResult, { job }));
    for (const c of job.result.cases) {
      assert.equal(c.nodeFlooding.durationMethod, 'NATIVE_EXTERNAL_FLOODING_END_STEP_SECONDS_V1');
      assert(c.nodeFlooding.nodes.some(n => n.floodingSeconds > 0));
    }
    const valid = job.result.numericalStatus === 'PASSED';
    assert.equal(html.includes('월류 발생 시간 · 설치 전'), valid);
    if (valid) assert(!html.includes('이 기록에는 시간 자료가 없습니다'));
    for (const mutate of [
      v => { delete v.result.cases[0].nodeFlooding.durationMethod; },
      v => { delete v.result.cases[1].nodeFlooding.nodes[0].floodingSeconds; },
      v => { v.result.cases[1].nodeFlooding.nodes[0].floodingSeconds = 1e20; },
      v => {
        delete v.result.cases[1].nodeFlooding.durationMethod;
        v.result.cases[1].nodeFlooding.nodes.forEach(n => { delete n.floodingSeconds; });
      },
    ]) {
      const changed = structuredClone(job);
      mutate(changed);
      assert(!watershedJobDto.safeParse(changed).success);
    }
    const record = { scenario, sourceResponseFile: source.slice(root.length + 1),
      sourceResponseSha256: createHash('sha256').update(raw).digest('hex'),
      numericalStatus: job.result.numericalStatus, dtoAndStaticRenderPassed: true };
    rows.push(record);
    if (scenario === 'S9-pipe' && process.argv.includes('--write-fixture')) {
      await writeFile(`${root}/frontend/src/domains/watershed/view/fixtures/public-node-flood-duration-v1.json`,
        JSON.stringify({ evidence: 'ACTUAL_HTTP_WORKER_RESULT_PROJECTION_NOT_BROWSER', ...record,
          layout: job.result.networkLayout.layout,
          baseline: job.result.cases[0].nodeFlooding, strategy: job.result.cases[1].nodeFlooding,
        }, null, 2) + '\n');
    }
  }
  await writeFile(`${root}/tmp/node-duration-readback-v1.json`,
    JSON.stringify({ schemaVersion: 1, scope: 'HTTP_WORKER_DTO_STATIC_RENDER_NOT_BROWSER', rows }, null, 2) + '\n');
  console.log(JSON.stringify({ status: 'PASSED', responses: rows.length }));
} finally {
  await server.close();
}
