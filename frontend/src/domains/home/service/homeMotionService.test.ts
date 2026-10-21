import { afterEach, expect, test, vi } from 'vitest';
import { startHomeMotion } from './homeMotionService';

afterEach(() => vi.unstubAllGlobals());

function setup(reduced = false) {
  const animation = {
    play: vi.fn(),
    pause: vi.fn(),
    cancel: vi.fn(),
    onfinish: null as (() => void) | null,
  };
  class Element extends EventTarget {
    dataset: Record<string, string> = {};
    animate = vi.fn(() => animation);
    parentElement = null;
    contains(node: unknown) {
      return node === this;
    }
  }
  const card = new Element();
  const root = Object.assign(new Element(), { querySelectorAll: () => [card] });
  const media = Object.assign(new EventTarget(), { matches: reduced });
  const document = Object.assign(new EventTarget(), { hidden: false });
  let notify: IntersectionObserverCallback;
  const observe = vi.fn();
  const disconnect = vi.fn();
  class Observer {
    constructor(callback: IntersectionObserverCallback) {
      notify = callback;
    }
    observe = observe;
    disconnect = disconnect;
  }
  vi.stubGlobal('Node', Element);
  vi.stubGlobal('document', document);
  vi.stubGlobal('window', { matchMedia: () => media, IntersectionObserver: Observer });
  vi.stubGlobal('IntersectionObserver', Observer);
  const cleanup = startHomeMotion(root as unknown as HTMLElement);
  const visible = (isIntersecting: boolean) =>
    notify(
      [{ target: card, isIntersecting } as unknown as IntersectionObserverEntry],
      {} as IntersectionObserver
    );
  return { animation, card, root, media, document, observe, disconnect, cleanup, visible };
}

test('화면 밖·숨긴 탭에서 정지하고 재진입 시 처음부터 반복하지 않는다', () => {
  const state = setup();
  state.visible(true);
  expect(state.card.animate).toHaveBeenCalledOnce();
  state.visible(false);
  expect(state.animation.pause).toHaveBeenCalledOnce();
  expect(state.card.dataset.homeActive).toBe('false');
  state.visible(true);
  expect(state.card.animate).toHaveBeenCalledOnce();
  state.document.hidden = true;
  state.document.dispatchEvent(new Event('visibilitychange'));
  expect(state.root.dataset.motionPaused).toBe('true');
  expect(state.animation.pause).toHaveBeenCalledTimes(2);
  state.document.hidden = false;
  state.document.dispatchEvent(new Event('visibilitychange'));
  expect(state.root.dataset.motionPaused).toBe('false');
  state.cleanup();
  expect(state.disconnect).toHaveBeenCalledOnce();
  expect(state.animation.cancel).toHaveBeenCalledOnce();
  expect(state.card.dataset).toEqual({});
  state.document.dispatchEvent(new Event('visibilitychange'));
  expect(state.root.dataset).toEqual({});
});

test('모션 축소 설정을 처음부터 존중하고 도중 변경 시 진행 모션도 취소한다', () => {
  const state = setup(true);
  state.visible(true);
  expect(state.card.animate).not.toHaveBeenCalled();
  state.cleanup();
  const active = setup();
  active.visible(true);
  active.media.matches = true;
  active.media.dispatchEvent(new Event('change'));
  expect(active.animation.cancel).toHaveBeenCalledOnce();
  active.cleanup();
});

test('키보드로 도달한 콘텐츠의 등장 지연을 없애고 미지원 기기에서도 내용을 유지한다', () => {
  const state = setup();
  state.visible(true);
  const event = new Event('focusin');
  Object.defineProperty(event, 'target', { value: state.card });
  state.root.dispatchEvent(event);
  expect(state.animation.cancel).toHaveBeenCalledOnce();
  state.cleanup();
  vi.stubGlobal('window', {});
  expect(() => startHomeMotion(state.root as unknown as HTMLElement)()).not.toThrow();
});
