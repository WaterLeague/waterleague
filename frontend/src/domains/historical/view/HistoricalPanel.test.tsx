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
    drafts: [
      {
        facilityType: 'GREEN_ROOF',
        site: { name: '복원 위치' },
        marker: { id: 'test-only', installedAt: '2022-08-08T09:02:17Z' },
      },
    ],
  } as HistoricalState;
  const html = renderToStaticMarkup(<HistoricalTimeline state={state} onInspect={() => {}} />);
  expect(html).toContain('재해 시간 재생');
  expect(html).not.toContain('설치 시각 목록');
});

test('설치 패널에서 전체 목록·제출·중복 게스트 안내와 수동 계산 제거', async () => {
  const { HistoricalPanel } = await import('./HistoricalPanel');
  const state = {
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
