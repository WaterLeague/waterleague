import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import fixture from './fixtures/public-network-result.json';
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
it('공통 시설창에 12군의 사용 범위를 구분하고 비회원 계산 결과 미노출', () => {
  const html = renderToStaticMarkup(
    <FacilityExpansionPanel
      account={null}
      open
      onClose={() => {}}
      onLogin={() => {}}
      onMapFacility={() => {}}
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
  expect(html).toContain('아직 설치하거나 이 화면에서 계산할 수 없습니다');
  expect(html).not.toContain('/bundle');
});
