import { expect, test } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { HistoricalTimeline } from './HistoricalPanel';
import type { HistoricalState } from '../controller/useHistorical';
import { HistoricalPanel } from './HistoricalPanel';
import nativeSites from '../../installation/__tests__/fixtures/nativeSites.json';
import { siteDto } from '../../installation/dto/installationDto';

test('설치 이용조의 초기 저류 비교를 회원에게만 제공하고 진행 중 요청 차단', () => {
  const site = siteDto.parse(nativeSites.reference);
  const draft = {
    site,
    facilityType: 'RAINWATER_CISTERN',
    areaM2: 235,
    marker: {
      id: 'test-cistern',
      facilityType: 'RAINWATER_CISTERN',
      areaM2: 235,
      cost: 2857130,
      ownerName: '시험',
      installedAt: '2022-08-08T09:02:17Z',
    },
  };
  const state = {
    facilityStates: [],
    drafts: [draft],
    design: { ready: true },
    calculationsReady: true,
    selectedRain: {},
    duration: 21540,
    elapsedSeconds: 200,
    remaining: 0,
  } as unknown as HistoricalState;
  const render = (authenticated: boolean, busy: boolean) =>
    renderToStaticMarkup(
      <HistoricalPanel
        state={{ ...state, busy }}
        site={site}
        type="RAINWATER_CISTERN"
        area="235"
        onType={() => {}}
        onArea={() => {}}
        authenticated={authenticated}
        error=""
        districtName="성동구"
      />
    );
  const member = render(true, false);
  expect(member).toContain('이 이용조의 시작 저류 비교');
  expect(member).toContain('자연배수·수요 인출 각각에서');
  expect(member).not.toContain('이 시설의 시작 수분 비교');
  expect(render(false, false)).not.toContain('이 이용조의 시작 저류 비교');
  expect(render(true, true)).toContain('disabled="">이 이용조의 시작 저류 비교');
});

test('설계가 사건 시간축보다 먼저 복원되어도 화면 유지', () => {
  const state = {
    event: undefined,
    duration: 0,
    frameCount: 0,
    facilityStates: [],
    drafts: [
      {
        facilityType: 'GREEN_ROOF',
        site: { name: '복원 위치' },
        marker: { id: 'test-only', installedAt: '2022-08-08T09:02:17Z' },
      },
    ],
  } as unknown as HistoricalState;
  const html = renderToStaticMarkup(<HistoricalTimeline state={state} onInspect={() => {}} />);
  expect(html).toContain('재해 시간 재생');
  expect(html).not.toContain('설치 시각 목록');
});

test('설치 패널에서 전체 목록·제출·중복 게스트 안내와 수동 계산 제거', async () => {
  const { HistoricalPanel } = await import('./HistoricalPanel');
  const state = {
    facilityStates: [],
    drafts: [],
    design: { ready: true },
    duration: 7200,
    elapsedSeconds: 180,
    budget: null,
    remaining: 2000000000,
  } as unknown as HistoricalState;
  const html = renderToStaticMarkup(
    <HistoricalPanel
      state={state}
      site={null}
      type=""
      area="10"
      onType={() => {}}
      onArea={() => {}}
      authenticated={false}
      error=""
      districtName="성동구"
    />
  );
  expect(html).not.toContain('설치 이후 효과 계산');
  expect(html).not.toContain('로그인 후 제출');
  expect(html).not.toContain('게스트 플레이');
  expect(html).not.toContain('체험 설계는 이 화면');
  expect(html).not.toContain('내 설치 시설');
});

test('설치 지점은 접힌 재생 도구 밖의 타임라인에 기본 표시', () => {
  const state = {
    event: {
      regions: [{ start: '2022-08-08T09:00:00Z' }],
      summary: '',
      evidenceUrl: '',
      evidenceTitle: '',
    },
    duration: 3600,
    frameCount: 60,
    elapsedSeconds: 1800,
    speed: 1,
    facilityStates: [],
    drafts: [
      {
        facilityType: 'PERMEABLE_PAVEMENT',
        site: { name: '차도 · 삼성로' },
        marker: { id: 'road', installedAt: '2022-08-08T09:00:04Z' },
      },
    ],
  } as unknown as HistoricalState;
  const html = renderToStaticMarkup(<HistoricalTimeline state={state} onInspect={() => {}} />);
  expect(html).toContain('타임라인 설치 기록');
  expect(html).toContain('18:00:04 투수포장 · 차도 · 삼성로');
  expect(html.indexOf('historical-time-pin')).toBeLessThan(
    html.indexOf('historical-playback-tools')
  );
});

import type { HistoricalDraft, HistoricalJob } from '../entity/historical';
import { historicalFacilityStates, temporalPolicy } from '../service/temporalService';

function effectFixture() {
  const site = siteDto.parse(nativeSites.reference);
  const drafts = ['first', 'second'].map((id) => ({
    site: { ...site, cellId: id },
    facilityType: 'RAINWATER_CISTERN',
    areaM2: 235,
    marker: {
      id,
      facilityType: 'RAINWATER_CISTERN',
      areaM2: 235,
      cost: 2857130,
      ownerName: '시험',
      installedAt: '2022-08-08T09:02:17Z',
    },
  })) as HistoricalDraft[];
  const job = {
    id: 'selected-district-job',
    districtId: site.districtId,
    modelHash: 'region',
    state: 'SUCCEEDED',
    placements: drafts.map((d) => ({
      districtId: site.districtId,
      cellId: d.site.cellId,
      siteModelHash: site.modelHash,
      facilityType: d.facilityType,
      areaM2: d.areaM2,
      temporalPolicy,
      installedAt: d.marker.installedAt,
    })),
    result: {
      engineVersion: '5.2.4',
      assumptions: [],
      temporalPolicy,
      facilities: drafts.map((d, i) => ({
        cellId: d.site.cellId,
        installedAt: d.marker.installedAt,
        frames: [
          {
            at: '2022-08-08T09:03:00Z',
            differenceM3: i ? -7 : 12,
            baselineAccountedM3: 30,
            designAccountedM3: i ? 37 : 18,
          },
          {
            at: '2022-08-08T09:04:00Z',
            differenceM3: 88,
            baselineAccountedM3: 100,
            designAccountedM3: 12,
          },
        ],
      })),
    },
  } as unknown as HistoricalJob;
  const state = {
    drafts,
    design: { ready: true },
    duration: 3600,
    elapsedSeconds: 200,
    remaining: 0,
    at: '2022-08-08T09:03:20Z',
    currentResult: job.result,
    currentScore: { differenceM3: 999 },
    job,
  } as unknown as HistoricalState;
  const render = (
    selectedSite = drafts[0].site,
    changes: Partial<HistoricalState> = {},
    authenticated = true
  ) => {
    const current = { ...state, ...changes };
    const facilityStates = historicalFacilityStates(
      [{ districtId: site.districtId, modelHash: 'region' }],
      current.drafts,
      { region: current.job! },
      current.at
    ).map((v) => ({ ...v, requestError: '' }));
    return renderToStaticMarkup(
      <HistoricalPanel
        state={{ ...current, facilityStates }}
        site={selectedSite}
        type="RAINWATER_CISTERN"
        area="235"
        onType={() => {}}
        onArea={() => {}}
        authenticated={authenticated}
        error=""
        districtName="성동구"
      />
    );
  };
  return { site, drafts, job, render };
}

test('시설 클릭은 구 합계 대신 선택 시설의 현재 분까지 효과·기준/설계 체적 표시', () => {
  const { drafts, render } = effectFixture();
  const first = render(drafts[0].site),
    second = render(drafts[1].site);
  expect(first).toContain('이 시설의 재생 시각까지 누적 효과');
  expect(first).toContain('12 m³');
  expect(first).toContain('<dd>18m³</dd>');
  expect(second).toContain('-7 m³');
  expect(second).toContain('<dd>37m³</dd>');
  expect(second).toContain('음수는 평가체적 증가');
  for (const html of [first, second]) {
    expect(html).not.toContain('999');
    expect(html).not.toContain('88 m³');
    expect(html).toContain('/api/v1/historical/selected-district-job/bundle');
  }
});

test('새 후보·설계 변경·재설치·계산 대기에는 기존 시설의 효과 미표시', () => {
  const { site, drafts, job, render } = effectFixture();
  const candidate = render(site);
  expect(candidate).not.toContain('재생 시각까지 누적 효과');
  expect(candidate).not.toContain('재현 자료 다운로드');
  for (const changes of [
    { drafts: [{ ...drafts[0], areaM2: 250 }, drafts[1]] },
    {
      drafts: [
        {
          ...drafts[0],
          marker: { ...drafts[0].marker, id: 'new-install', installedAt: '2022-08-08T09:03:10Z' },
        },
        drafts[1],
      ],
    },
    { job: { ...job, state: 'RUNNING' as const } },
  ]) {
    const html = render(drafts[0].site, changes);
    expect(html).not.toContain('12 m³');
    expect(html).not.toContain('999');
    expect(html).toContain('이 시설의 누적 효과 계산을 기다리는 중');
  }
});

test('설치 이전·첫 분 기록 이전·게스트 종료 시각의 점수 노출 경계 유지', () => {
  const { drafts, render } = effectFixture();
  const before = render(drafts[0].site, { at: '2022-08-08T09:02:00Z' });
  expect(before).toContain('설치 전');
  expect(before).not.toContain('12 m³');
  expect(render(drafts[0].site, { at: '2022-08-08T09:02:30Z' })).toContain('누적 기록 없음');
  expect(render(drafts[0].site, { elapsedSeconds: 3600 }, false)).not.toContain(
    '재생 시각까지 누적 효과'
  );
});
