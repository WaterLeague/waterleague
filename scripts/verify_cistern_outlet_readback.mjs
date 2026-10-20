import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { createServer } from '../frontend/node_modules/vite/dist/node/index.js';

const root = resolve(import.meta.dirname, '..');
assert(process.argv[2], '격리 관망 시험의 .fixtures 폴더 필요');
const directory = resolve(process.argv[2]);
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
  for (const scenario of ['S9-outlets', 'S9-outletflood', 'S9-outlets-reused', 'S9-outletflood-reused']) {
    const source = resolve(directory, `api-view-${scenario}.json`);
    const raw = await readFile(source);
    const job = watershedJobDto.parse(JSON.parse(raw));
    const pipes = job.result.cases[1].networkCistern.wholeRunLedger.outletPipes;
    const html = renderToStaticMarkup(React.createElement(WatershedResult, { job }));
    for (const kind of ['drain', 'overflow']) {
      assert(job.design.cistern[`${kind}Pipe`]);
      assert.equal(pipes[kind].receiverNodeId, 'J22');
      assert(html.includes(`${kind === 'drain' ? '일반' : '비상'} 배수 연결관 · 길이 10`));
      assert(html.includes(`${kind === 'drain' ? '일반' : '비상'} 배수 연결관 접속부`));
    }
    if (scenario.includes('outletflood')) {
      assert(pipes.drain.floodingM3 > 0);
      assert.equal(pipes.drain.numericalStatus, 'FAILED');
      assert.equal(job.result.signedReductionM3, null);
      assert(html.includes('효과 비교 보류'));
    } else {
      assert.equal(job.result.numericalStatus, 'PASSED');
      assert.equal(pipes.drain.floodingM3, 0);
    }
    const row = { scenario, sourceResponseFile: source.slice(root.length + 1),
      sourceResponseSha256: createHash('sha256').update(raw).digest('hex'),
      numericalStatus: job.result.numericalStatus, outletPipes: pipes,
      dtoAndStaticRenderPassed: true };
    rows.push(row);
    if (process.argv.includes('--write-fixtures') && !scenario.endsWith('-reused')) {
      await writeFile(`${root}/frontend/src/domains/watershed/view/fixtures/public-cistern-${scenario.slice(3)}-job-v1.json`,
        JSON.stringify({ evidence: 'ACTUAL_AUTHENTICATED_HTTP_WORKER_PROJECTION_NOT_BROWSER',
          sourceResponseFile: row.sourceResponseFile, sourceResponseSha256: row.sourceResponseSha256,
          job }, null, 2) + '\n');
    }
  }
  await writeFile(`${root}/tmp/cistern-outlet-readback-v1.json`,
    JSON.stringify({ schemaVersion: 1, rows }, null, 2) + '\n');
  console.log(JSON.stringify({ status: 'PASSED', responses: rows.length }));
} finally {
  await server.close();
}
