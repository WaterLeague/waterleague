import { expect, test } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { HistoricalTimeline } from './HistoricalPanel';
import type { HistoricalState } from '../controller/useHistorical';

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

test('비회원도 누적 효과와 계산 버튼을 사용하고 제출은 로그인 요구', async () => {
  const { HistoricalPanel } = await import('./HistoricalPanel');
  const draft = {
    site: { districtId: '2419953', cellId: 'QA', name: '시험 위치' },
    facilityType: 'GREEN_ROOF',
    areaM2: 10,
    marker: { id: 'qa', installedAt: '2022-08-08T09:02:17Z' },
  };
  const state = {
    drafts: [draft],
    current: [draft],
    facilityStates: [
      { draft, before: false, score: { differenceM3: -0.25, at: '2022-08-08T09:03:00Z' } },
    ],
    calculationsReady: true,
    busy: false,
    job: null,
    currentResult: null,
    lab: {},
    design: { ready: true, revision: 0, saving: false, loading: false, error: '', guestCount: 0 },
    submission: { records: [], busy: false, error: '', conflict: false },
    duration: 7200,
    elapsedSeconds: 180,
    budget: null,
    accounting: null,
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
      onLogin={() => {}}
      authenticated={false}
      error=""
      districtName="성동구"
      onInspect={() => {}}
    />
  );
  expect(html).toContain('누적 -0.25');
  expect(html).toContain('설치 이후 효과 계산');
  expect(html).not.toContain('로그인 후 계산');
  expect(html).not.toContain('로그인 후 누적 효과 계산');
  expect(html).toContain('로그인 후 제출');
  expect(html).not.toContain('재현 자료 다운로드');
});
