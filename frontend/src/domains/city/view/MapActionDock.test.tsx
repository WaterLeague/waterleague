import { expect, test } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import type { HistoricalState } from '../../historical/controller/useHistorical';
import type { Account } from '../../account/entity/account';
import { MapActionDock } from './MapActionDock';
function markup(count: number, account: Account | null = null, ready = true) {
  const state = {
    drafts: Array.from({ length: count }, () => ({})),
    design: { ready, guestCount: 0 },
    submission: { records: [], busy: false },
    duration: 100,
    elapsedSeconds: 0,
    remaining: 0,
    budget: null,
  } as unknown as HistoricalState;
  return renderToStaticMarkup(
    <MapActionDock
      historical
      research={state}
      account={account}
      budget={null}
      remaining={0}
      ownInstallations={[]}
      districts={[]}
      onLogin={() => {}}
      onInspect={() => {}}
      onHistoricalInspect={() => {}}
    >
      <button>시설 설치하기</button>
    </MapActionDock>
  );
}
test('빈 설계는 제출 비활성화·목록 숨김, 설치 뒤 목록과 로그인 제출 활성화', () => {
  const empty = markup(0);
  expect(empty).not.toContain('설치한 시설 보기');
  expect(empty).toMatch(/class="submit-action" disabled=""/);
  const placed = markup(1);
  expect(placed).toContain('설치한 시설 보기');
  expect(placed).toContain('로그인 후 제출하기');
  expect(placed).not.toMatch(/class="submit-action" disabled/);
  expect(placed).not.toContain('설치 이후 효과 계산');
  expect(placed).not.toContain('게스트 플레이');
});
test('회원 제출과 설계 복원 중 제출 차단 유지', () => {
  expect(markup(1, { id: 'test' } as Account)).toContain('제출하기');
  expect(markup(1, null, false)).toMatch(/class="submit-action" disabled=""/);
});
