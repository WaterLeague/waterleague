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
    const summary = job.result.cases[1].networkCistern;
    const inlet = summary.wholeRunLedger.inletPipe;
    const html = renderToStaticMarkup(React.createElement(WatershedResult, { job }));
    assert.equal(Boolean(inlet), Boolean(job.design.cistern.inletPipe));
    if (inlet) {
      assert(html.includes('집수 연결관 · 길이 10'));
      assert(html.includes('집수 연결관 입구'));
      const flooded = scenario === 'S9-narrow';
      assert.equal(inlet.numericalStatus, flooded ? 'FAILED' : 'PASSED');
      if (flooded) {
        assert(inlet.floodingM3 > 0);
        assert(html.includes('효과 비교 보류'));
        assert.equal(job.result.signedReductionM3, null);
      } else {
        assert.equal(inlet.floodingM3, 0);
      }
      for (const mutate of [
        (v) => { delete v.design.cistern.inletPipe; },
        (v) => { delete v.result.cases[1].networkCistern.wholeRunLedger.inletPipe; },
        (v) => { v.result.cases[1].networkCistern.wholeRunLedger.inletPipe.nodeId = 'Unbound'; },
        (v) => { v.result.cases[1].networkCistern.wholeRunLedger.inletPipe.floodingM3 += 1; },
      ]) {
        const changed = structuredClone(job);
        mutate(changed);
        assert(!watershedJobDto.safeParse(changed).success);
      }
    }
    rows.push({ scenario, sourceResponseFile: source,
      sourceResponseSha256: createHash('sha256').update(raw).digest('hex'),
      numericalStatus: job.result.numericalStatus, ledger: summary.wholeRunLedger,
      dtoAndStaticRenderPassed: true });
    if (inlet && process.argv.includes('--write-fixtures')) {
      const fixture = { evidence: 'ACTUAL_API_WORKER_DTO_PROJECTION_NOT_AUTHENTICATED_BROWSER',
        sourceResponseFile: source.slice(root.length + 1),
        sourceResponseSha256: rows.at(-1).sourceResponseSha256, job };
      await writeFile(`${root}/frontend/src/domains/watershed/view/fixtures/public-cistern-${scenario === 'S9-pipe' ? 'inlet' : 'inlet-flood'}-job-v1.json`,
        JSON.stringify(fixture, null, 2) + '\n');
    }
  }
  const report = { schemaVersion: 1, status: 'PASSED',
    scope: 'ISOLATED_HTTP_WORKER_DTO_STATIC_RENDER_NOT_BROWSER', rows };
  await writeFile(`${root}/tmp/cistern-inlet-readback-v1.json`, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ status: report.status, responses: rows.length }));
} finally {
  await server.close();
}
