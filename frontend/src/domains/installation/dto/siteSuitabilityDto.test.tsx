import { expect, test } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { conditionIds, siteSuitabilityDto } from './siteSuitabilityDto';
import { siteDto } from './installationDto';
import { SiteSuitabilityEvidence } from '../view/SiteSuitabilityEvidence';
import { FacilityPlacementPanel } from '../view/FacilityPlacementPanel';
import nativeSites from '../__tests__/fixtures/nativeSites.json';

const report = {
  version: 'SITE_SUITABILITY_V1',
  policySha256: 'a'.repeat(64),
  status: 'UNKNOWN',
  explorationAllowed: true,
  constructionApproved: false,
  checks: conditionIds.GROUND.map((id) => ({
    id,
    status: 'UNKNOWN',
    reason: '시험 전용 · 현장 근거 미확인',
    evidence: null,
  })),
};

test('미확인 조건을 허용·시공 승인·가짜 근거로 승격한 응답 거부', () => {
  expect(siteSuitabilityDto.safeParse(report).success).toBe(true);
  for (const value of [
    { ...report, status: 'ELIGIBLE' },
    { ...report, constructionApproved: true },
    { ...report, checks: report.checks.slice(1) },
    { ...report, checks: [report.checks[0], ...report.checks.slice(0, -1)] },
    { ...report, status: 'PROHIBITED' },
    { ...report, checks: report.checks.map((row) => ({ ...row, status: 'ELIGIBLE' })) },
  ])
    expect(siteSuitabilityDto.safeParse(value).success).toBe(false);
  expect(
    siteDto.safeParse({
      ...nativeSites.reference,
      suitability: report,
      siteEligibility: 'ELIGIBLE',
    }).success
  ).toBe(false);
});

test('미확인 세부 조건과 실제 시공 승인 구분을 같은 근거 화면에 표시', () => {
  const html = renderToStaticMarkup(
    <SiteSuitabilityEvidence value={siteSuitabilityDto.parse(report)} />
  );
  for (const text of [
    '현장 토양',
    '현장 경사',
    '지하수',
    '지하 지장물',
    '교통 하중',
    '배수',
    '미확인',
    '실제 시공 승인이 아닙니다',
  ])
    expect(html).toContain(text);
});

test('주간·재해 공통 폼은 금지·조건부 후보의 설치 차단', () => {
  for (const research of [false, true])
    for (const status of ['UNKNOWN', 'PROHIBITED', 'CONDITIONAL']) {
      const restricted = status !== 'UNKNOWN';
      const suitability = { ...report, status, explorationAllowed: !restricted };
      const site = siteDto.parse({
        ...nativeSites.reference,
        siteEligibility: status,
        suitability,
      });
      const html = renderToStaticMarkup(
        <FacilityPlacementPanel
          site={site}
          type="PERMEABLE_PAVEMENT"
          area="1"
          onType={() => {}}
          onArea={() => {}}
          onInstall={() => {}}
          districtName="시험"
          context="시험 전용"
          budget={null}
          remaining={2000000000}
          limit={2000000000}
          budgetReady
          busy={false}
          canInstall
          research={research}
          budgetAccounting={{
            version: 'TEST_ONLY',
            programs: [],
            facilities: [
              {
                facilityType: 'PERMEABLE_PAVEMENT',
                programId: 'TEST_ONLY',
                limitKrw: null,
                allocatedKrw: 0,
                availableKrw: 2000000000,
              },
            ],
          }}
        />
      );
      expect(html.includes('미충족 안전 조건')).toBe(restricted);
      expect(
        html.match(/<button class="solid-button shared-install"[^>]*>/)?.[0]?.includes('disabled')
      ).toBe(restricted);
    }
});
