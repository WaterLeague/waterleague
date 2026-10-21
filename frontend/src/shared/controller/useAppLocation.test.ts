import { afterEach, describe, expect, it, vi } from 'vitest';
import { navigate, followLink } from './useAppLocation';
import type { MouseEvent } from 'react';
afterEach(() => vi.unstubAllGlobals());
function location() {
  const events: Event[] = [];
  const fake = {
    location: { origin: 'http://localhost:5173', pathname: '/', search: '', hash: '' },
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
  it('같은 데이터 링크를 다시 눌러도 위치를 이동하고 방문 이력을 중복하지 않는다', () => {
    const { fake } = location();
    fake.location.hash = '#home-data';
    const scrollIntoView = vi.fn();
    const getElementById = vi.fn(() => ({ scrollIntoView }));
    vi.stubGlobal('document', { getElementById });
    navigate('/#home-data');
    expect(getElementById).toHaveBeenCalledWith('home-data');
    expect(scrollIntoView).toHaveBeenCalledOnce();
    expect(fake.history.pushState).not.toHaveBeenCalled();
  });
  it('홈 데이터 앵커와 검색 조건을 보존하며 이전 주소를 교체한다', () => {
    const { fake, events } = location();
    navigate('/#home-data', true);
    navigate('/?from=weekly#home-data');
    expect(fake.history.replaceState).toHaveBeenCalledWith(null, '', '/#home-data');
    expect(fake.history.pushState).toHaveBeenCalledWith(null, '', '/?from=weekly#home-data');
    expect(events).toHaveLength(2);
  });
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
