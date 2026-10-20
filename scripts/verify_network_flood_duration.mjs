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
    const result = job.result;
    const metric = result.metricComparison.metrics.find(m => m.id === 'networkFloodingSeconds');
    const html = renderToStaticMarkup(React.createElement(WatershedResult, { job }));
    for (const c of result.cases) {
      const duration = c.evaluationMetrics.floodingDuration;
      assert(duration.complete);
      assert(duration.floodingSeconds > 0);
      assert(duration.floodingSeconds < c.nodeFlooding.nodes.reduce((s, n) => s + n.floodingSeconds, 0));
    }
    const valid = result.numericalStatus === 'PASSED';
    assert.equal(metric.status, valid ? 'COMPARABLE' : 'WITHHELD');
    assert(html.includes('관망 전체 월류 발생 시간'));
    assert(html.includes('번만 계산하며'));
    assert.equal(html.includes('월류 시간 효과 비교 보류'), !valid);
    assert.equal(metric.baseline, result.cases[0].evaluationMetrics.floodingDuration.floodingSeconds);
    assert.equal(metric.strategy, result.cases[1].evaluationMetrics.floodingDuration.floodingSeconds);
    for (const mutate of [
      v => { delete v.result.cases[1].evaluationMetrics.floodingDuration; },
      v => { v.result.cases[1].evaluationMetrics.floodingDuration.coveredSeconds -= 1; },
      v => { v.result.cases[1].evaluationMetrics.floodingDuration.startSeconds = 1; },
      v => { v.result.cases[1].evaluationMetrics.floodingDuration.floodingSeconds += 1; },
      v => { v.result.cases[1].evaluationMetrics.floodingDuration.method = 'SUM_NODE_SECONDS'; },
      v => {
        const c = v.result.cases[1];
        c.evaluationMetrics.floodingDuration.floodingSeconds = c.nodeFlooding.nodes.reduce((s, n) => s + n.floodingSeconds, 0);
      },
    ]) {
      const changed = structuredClone(job); mutate(changed);
      assert(!watershedJobDto.safeParse(changed).success);
    }
    const record = { scenario, sourceResponseFile: source.slice(root.length + 1),
      sourceResponseSha256: createHash('sha256').update(raw).digest('hex'),
      numericalStatus: result.numericalStatus, metric,
      dtoAndStaticRenderPassed: true };
    rows.push(record);
    if (scenario === 'S9-pipe' && process.argv.includes('--write-fixture')) {
      await writeFile(`${root}/frontend/src/domains/watershed/view/fixtures/public-network-flood-duration-v1.json`,
        JSON.stringify({ evidence: 'ACTUAL_HTTP_WORKER_RESULT_PROJECTION_NOT_BROWSER', ...record,
          comparison: result.metricComparison,
          baseline: result.cases[0].evaluationMetrics, strategy: result.cases[1].evaluationMetrics,
        }, null, 2) + '\n');
    }
  }
  await writeFile(`${root}/tmp/network-duration-readback-v1.json`,
    JSON.stringify({ schemaVersion: 1, scope: 'HTTP_WORKER_DTO_STATIC_RENDER_NOT_BROWSER', rows }, null, 2) + '\n');
  console.log(JSON.stringify({ status: 'PASSED', responses: rows.length }));
} finally {
  await server.close();
}
