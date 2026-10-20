import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import fixture from './fixtures/public-network-result.json';
import peaks from './fixtures/public-network-peaks.json';
import { watershedJobDto, watershedResultDto } from '../dto/watershedDto';
import { WatershedResult } from './WatershedResult';
import { FacilityExpansionPanel } from './FacilityExpansionPanel';
const job = () =>
  watershedJobDto.parse({
    id: '10000000-0000-4000-8000-000000000001',
    catalogHash: fixture.catalogHash,
    state: 'SUCCEEDED',
    createdAt: '2026-10-18T00:00:00Z',
    message: '',
    result: fixture,
    design: {
      placements: [
        {
          id: 'Bio1',
          facilityType: 'BIORETENTION',
          subcatchmentId: 'S1',
          areaM2: 100,
          treatedImperviousM2: 1000,
        },
      ],
    },
  });
it('기준안·설계안별 계산 재사용을 구분하고 잘못된 실행 근거 거부', () => {
  const value = job();
  value.result!.cases.forEach((c, i) => {
    c.execution = {
      schema: 1,
      scope: 'PUBLIC_NETWORK_CASE_V1',
      mode: i === 0 ? 'REUSED' : 'COMPUTED',
      computationKey: 'a'.repeat(64),
    };
  });
  const html = renderToStaticMarkup(<WatershedResult job={watershedJobDto.parse(value)} />);
  expect(html).toContain('동일 조건의 검증된 계산 결과 재사용');
  expect(html).toContain('이번 요청에서 새로 계산');
  for (const change of [
    { schema: 2 },
    { scope: 'OTHER' },
    { mode: 'CACHED' },
    { computationKey: 'invalid' },
    { ownerId: 'PRIVATE' },
  ]) {
    const changed = structuredClone(value);
    Object.assign(changed.result!.cases[0].execution!, change);
    expect(watershedJobDto.safeParse(changed).success).toBe(false);
  }
  expect(renderToStaticMarkup(<WatershedResult job={job()} />)).not.toContain(
    '이번 요청에서 새로 계산'
  );
});
it('실제 관망 결과의 월류 감소와 외부 방류 증가를 별도 표시', () => {
  const html = renderToStaticMarkup(<WatershedResult job={job()} />);
  expect(html).toContain('51.338');
  expect(html).toContain('5.1454');
  expect(html).toContain('증가');
  expect(html).toContain('-5.1454');
  expect(html).toContain('현장 정확도 검증과 구분');
  expect(html).toContain('/bundle');
  expect(html).not.toContain('0원');
});
it('수치 실패 결과의 효과 비교를 보류하고 원시 실패 문자열 비노출', () => {
  const result = {
    ...fixture,
    numericalStatus: 'FAILED',
    signedReductionM3: null,
    cases: [
      fixture.cases[0],
      { id: 'strategy', numericalStatus: 'FAILED', failureCode: 'SECRET_INTERNAL_PATH' },
    ],
  };
  const failed = watershedJobDto.parse({ ...job(), result });
  const html = renderToStaticMarkup(<WatershedResult job={failed} />);
  expect(html).toContain('효과 비교 보류');
  expect(html).not.toContain('51.338');
  expect(html).not.toContain('SECRET_INTERNAL_PATH');
  expect(html).toContain('/bundle');
  expect(
    watershedResultDto.safeParse({ ...result, signedReductionM3: fixture.signedReductionM3 })
      .success
  ).toBe(false);
});
it('중복 기준안·변화 부호 불일치·다른 카탈로그 결과 거부', () => {
  expect(
    watershedResultDto.safeParse({ ...fixture, cases: [fixture.cases[0], fixture.cases[0]] })
      .success
  ).toBe(false);
  expect(
    watershedResultDto.safeParse({
      ...fixture,
      signedReductionM3: { ...fixture.signedReductionM3, outflowM3: 5.145423324778676 },
    }).success
  ).toBe(false);
  expect(watershedJobDto.safeParse({ ...job(), catalogHash: 'f'.repeat(64) }).success).toBe(false);
});
it('공통 시설창의 사업별 12군과 이용조 계획 진입·미구현 설치 구분', () => {
  const html = renderToStaticMarkup(
    <FacilityExpansionPanel
      account={null}
      open
      onClose={() => {}}
      onLogin={() => {}}
      onMapFacility={() => {}}
      onCisternPlan={() => {}}
    />
  );
  for (const name of [
    '빗물정원',
    '투수포장',
    '녹화지붕',
    '생물저류시설',
    '침투 트렌치',
    '식생수로',
    '빗물이용조',
    '지하 저류조',
    '저류지·유수지',
    '빗물받이',
    '배수관·암거',
    '빗물펌프장',
  ])
    expect(html).toContain(name);
  expect(html).not.toContain('설치 연결 중');
  expect(html.match(/disabled=""/g)).toHaveLength(5);
  const cisternButton = html
    .match(/<button\b[^>]*>[\s\S]*?<\/button>/g)
    ?.find((button) => button.includes('<strong>빗물이용조</strong>'));
  expect(cisternButton).toContain('지도 계획 작성 · 설치 없음');
  expect(cisternButton).not.toContain('disabled');
  const withoutPlan = renderToStaticMarkup(
    <FacilityExpansionPanel
      account={null}
      open
      onClose={() => {}}
      onLogin={() => {}}
      onMapFacility={() => {}}
    />
  );
  expect(withoutPlan.match(/disabled=""/g)).toHaveLength(6);
  expect(withoutPlan).not.toContain('지도 계획 작성');
  for (const project of [
    '빗물관리시설 확충',
    '빗물저류시설 확충',
    '하수관로·빗물받이 정비',
    '빗물펌프장 신·증설',
  ])
    expect(html).toContain(project);
  expect(html).not.toContain('연결 유역 비교');
  expect(html).not.toContain('지도에 설치');
  expect(html.match(/생물저류시설/g)).toHaveLength(1);
  expect(html).not.toContain('/bundle');
});
const withPeaks = () => ({
  ...fixture,
  signedPeakReductionM3s: peaks.signedPeakReductionM3s,
  cases: fixture.cases.map((c) => ({
    ...c,
    evaluationMetrics: peaks.cases.find((p) => p.id === c.id)!.evaluationMetrics,
  })),
});
it('실제 관망의 첨두 변화 없음과 출구별 발생 시각 표시', () => {
  const result = watershedResultDto.parse(withPeaks());
  const html = renderToStaticMarkup(<WatershedResult job={{ ...job(), result }} />);
  expect(html).toContain('외부 출구 동시 합계 첨두');
  expect(html).toContain('39.041');
  expect(html).toContain('변화 없음');
  expect(html).toContain('Out1');
  expect(html).toContain('Out2');
  expect(html).toContain('14시간 24분 53.095초');
  expect(renderToStaticMarkup(<WatershedResult job={job()} />)).toContain(
    '출구 첨두가 수집되지 않았습니다'
  );
});
it('첨두 악화 보존과 평가 기간·출구·부호·실패 불일치 차단', () => {
  const worse = withPeaks();
  worse.cases = structuredClone(worse.cases);
  worse.cases[1].evaluationMetrics.combined.peakOutwardM3s += 1;
  worse.signedPeakReductionM3s = -1;
  const html = renderToStaticMarkup(
    <WatershedResult job={{ ...job(), result: watershedResultDto.parse(worse) }} />
  );
  expect(html).toContain('1 m³/s 증가');
  for (const change of ['sign', 'window', 'outfall', 'incomplete', 'failed']) {
    const bad = structuredClone(worse);
    if (change === 'sign') bad.signedPeakReductionM3s = 1;
    if (change === 'window') bad.cases[1].evaluationMetrics.specification.endMilliseconds -= 1000;
    if (change === 'outfall')
      bad.cases[1].evaluationMetrics.specification.networkOutfalls = ['Out1'];
    if (change === 'incomplete') bad.cases[1].evaluationMetrics.complete = false;
    if (change === 'failed') {
      bad.numericalStatus = 'FAILED';
    }
    expect(watershedResultDto.safeParse(bad).success, change).toBe(false);
  }
});
