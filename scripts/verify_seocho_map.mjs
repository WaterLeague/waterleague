import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { createServer } from '../frontend/node_modules/vite/dist/node/index.js';

const root = resolve(import.meta.dirname, '..');
const directory = process.argv[2];
assert(directory, '서버·워커 관망 시험의 .fixtures 폴더 필요');
const source = resolve(directory, 'location-result');
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const manifestRaw = await readFile(`${source}/manifest.json`);
const manifest = JSON.parse(manifestRaw);
for (const [name, hash] of Object.entries(manifest)) {
  assert(!name.startsWith('/') && !name.split('/').includes('..'));
  assert.equal(digest(await readFile(`${source}/${name}`)), hash);
}
const requestRaw = await readFile(resolve(directory, 'location-server-request.json'));
const request = JSON.parse(requestRaw);
assert.equal(request.inputHash, digest(`${request.modelHash}\n${request.placements}`));
const resultRaw = await readFile(`${source}/result.json`);
const result = JSON.parse(resultRaw);
const design = JSON.parse(request.placements);
assert.equal(result.inputHash, request.inputHash);
assert.equal(result.numericalStatus, 'PASSED');
assert.deepEqual(result.locationReference, design.locationReference);
assert.equal(manifest['location-profile.json'], design.locationReference.profileSha256);
assert.equal(design.placements[0].subcatchmentId, 'S2');
const require = createRequire(`${root}/frontend/package.json`);
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const server = await createServer({ root: `${root}/frontend`, server: { middlewareMode: true }, appType: 'custom' });
try {
  const { watershedJobDto } = await server.ssrLoadModule('/src/domains/watershed/dto/watershedDto.ts');
  const { WatershedResult } = await server.ssrLoadModule('/src/domains/watershed/view/WatershedResult.tsx');
  // 식별자·시각은 화면 검사 전용이며 원 계산 입력과 결과는 수정하지 않는다.
  const job = watershedJobDto.parse({ id: '10000000-0000-4000-8000-000000000001',
    catalogHash: request.modelHash, state: 'SUCCEEDED', createdAt: '2026-10-21T00:00:00Z',
    message: '', design, result });
  const html = renderToStaticMarkup(React.createElement(WatershedResult, { job }));
  assert(html.includes('지도 위치 가정 EPSG:5181'));
  assert(html.includes('S2'));
  let rejected = 0;
  for (const mutate of [
    value => { value.result.locationReference.profileSha256 = '0'.repeat(64); },
    value => { delete value.result.locationReference; },
    value => { delete value.design.locationReference; },
    value => { value.result.locationReference.sourceCrsVerified = true; },
    value => { value.result.locationReference.assumedSourceCrs = 'EPSG:5174'; },
  ]) {
    const invalid = structuredClone(job);
    mutate(invalid);
    assert.equal(watershedJobDto.safeParse(invalid).success, false);
    rejected++;
  }
  const report = { schemaVersion: 1, scope: 'SERVER_REQUEST_NATIVE_WORKER_DTO_STATIC_RENDER_NOT_BROWSER_HTTP',
    requestSha256: digest(requestRaw), inputHash: request.inputHash, resultSha256: digest(resultRaw),
    manifestSha256: digest(manifestRaw), artifactsVerified: Object.keys(manifest).length,
    locationReference: result.locationReference, placements: design.placements,
    numericalStatus: result.numericalStatus, signedReductionM3: result.signedReductionM3,
    signedPeakReductionM3s: result.signedPeakReductionM3s, metricComparison: result.metricComparison,
    cases: result.cases.map(c => ({ id: c.id, totals: c.totals, numericalStatus: c.numericalStatus,
      evaluationMetrics: c.evaluationMetrics })),
    dtoAndStaticRenderPassed: true, invalidLocationCasesRejected: rejected };
  await writeFile(`${root}/tmp/seocho-map-worker-readback-v1.json`, JSON.stringify(report, null, 2)+'\n');
  console.log(JSON.stringify({ status: 'PASSED', artifacts: report.artifactsVerified, invalidLocationCasesRejected: rejected }));
} finally {
  await server.close();
}
