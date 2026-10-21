import { afterEach, describe, expect, it, vi } from 'vitest';
import { navigate, followLink } from './useAppLocation';
import type { MouseEvent } from 'react';
afterEach(() => vi.unstubAllGlobals());
function location() {
  const events: Event[] = [];
  const fake = {
    location: { origin: 'http://localhost:5173' },
    history: { pushState: vi.fn(), replaceState: vi.fn() },
    dispatchEvent: (e: Event) => {
      events.push(e);
      return true;
    },
  };
  vi.stubGlobal('window', fake);
  vi.stubGlobal('PopStateEvent', Event);
  return { fake, events };
}
describe('독립 페이지 주소 이동', () => {
  it('검색 조건을 보존하고 주소 교체와 신규 방문을 구분한다', () => {
    const { fake, events } = location();
    navigate('/weekly', true);
    navigate('/disaster/rain?competition=123');
    expect(fake.history.replaceState).toHaveBeenCalledWith(null, '', '/weekly');
    expect(fake.history.pushState).toHaveBeenCalledWith(null, '', '/disaster/rain?competition=123');
    expect(events.map((e) => e.type)).toEqual(['popstate', 'popstate']);
    navigate('https://external.invalid/');
    expect(fake.history.pushState).toHaveBeenCalledTimes(1);
  });
  it('새 탭 열기는 기본 링크 동작을 보존한다', () => {
    const { fake } = location();
    const preventDefault = vi.fn();
    followLink(
      { button: 0, ctrlKey: true, preventDefault } as unknown as MouseEvent<HTMLAnchorElement>,
      '/rankings'
    );
    expect(preventDefault).not.toHaveBeenCalled();
    expect(fake.history.pushState).not.toHaveBeenCalled();
    followLink(
      { button: 0, preventDefault } as unknown as MouseEvent<HTMLAnchorElement>,
      '/competitions'
    );
    expect(preventDefault).toHaveBeenCalledOnce();
    expect(fake.history.pushState).toHaveBeenCalledWith(null, '', '/competitions');
  });
});
