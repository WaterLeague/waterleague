import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { CompetitionResults } from './CompetitionResults';
import { CompetitionForm } from './CompetitionForm';
import type { CompetitionCatalog, CompetitionResults as Results } from '../dto/competitionDto';
const catalog: CompetitionCatalog = {
  districts: [{ id: '11680', name: '강남구' }],
  events: [{ id: 'rain', title: '시험 강우' }],
  facilityTypes: ['RAIN_GARDEN'],
  serverNow: '2026-10-21T00:00:00Z',
};
const id = '00000000-0000-4000-8000-000000000001';
const result: Results = {
  competition: {
    id,
    title: '시험 대회',
    description: '시험',
    organizationName: '시험 기관',
    mode: 'REALTIME',
    eventId: null,
    opensAt: catalog.serverNow,
    closesAt: '2026-10-28T00:00:00Z',
    phase: 'ENDED',
    rulesHash: 'a'.repeat(64),
    canManage: true,
    joinedAt: null,
    participantCount: 1,
    rules: {
      districtIds: ['11680'],
      allowedTypes: ['RAIN_GARDEN'],
      awards: [],
      awardNotice: '',
      scorePolicySha256: 'b'.repeat(64),
    },
  },
  status: 'FINAL',
  page: 0,
  hasMore: false,
  missingSeconds: 0,
  pendingCalculations: false,
  generatedAt: catalog.serverNow,
  groups: [
    {
      comparisonGroup: 'c'.repeat(64),
      count: 1,
      entries: [
        {
          playerId: id,
          nickname: '<script>unsafe</script>',
          rank: 1,
          scoreM3: -0.000000001,
          scoreM3Exact: '-0.000000001',
          comparable: true,
          submittedAt: catalog.serverNow,
          installations: [
            {
              id,
              playerId: id,
              districtId: '11680',
              facilityType: 'RAIN_GARDEN',
              areaM2: 20,
              installedAt: catalog.serverNow,
            },
          ],
        },
      ],
    },
  ],
};
it('실시간 기록에 설치 시각과 음수 원점수를 표시하고 사용자 문자열을 이스케이프한다', () => {
  const html = renderToStaticMarkup(
    <CompetitionResults value={result} catalog={catalog} onPage={() => {}} />
  );
  expect(html).toContain('설치 시각');
  expect(html).toContain('빗물정원');
  expect(html).toContain('-0.000000001 m³');
  expect(html).not.toContain('<script>');
});
it('재해 결과에는 시설 설치 기간 대신 제출 시각만 표시한다', () => {
  const html = renderToStaticMarkup(
    <CompetitionResults
      value={{
        ...result,
        competition: { ...result.competition, mode: 'DISASTER', eventId: 'rain' },
      }}
      catalog={catalog}
      onPage={() => {}}
    />
  );
  expect(html).toContain('제출 시각');
  expect(html).not.toContain('설치 시각');
  expect(html).not.toContain('빗물정원');
});
it('개최 폼에 요청한 조건과 명시적 공개 확인을 제공한다', () => {
  const html = renderToStaticMarkup(
    <CompetitionForm catalog={catalog} onCreated={() => {}} onClose={() => {}} />
  );
  for (const label of [
    '대회 이름',
    '대회 소개',
    '실시간 모드',
    '재해 모드',
    '서울 전체',
    '강남구',
    '설치 가능 시설',
    '시상 규모',
    '시상 및 운영 안내',
    '대회 공개하기',
  ])
    expect(html).toContain(label);
});
