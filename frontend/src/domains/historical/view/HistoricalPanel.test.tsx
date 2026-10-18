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
