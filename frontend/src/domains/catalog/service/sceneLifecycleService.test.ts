import { describe, expect, it, vi } from 'vitest';
import { watchContextLoss } from './sceneLifecycleService';

describe('지도 그래픽 연결 손실', () => {
  it('손실 이벤트에서 한 번만 대안 화면을 요청하고 정리 후 이벤트를 무시한다', () => {
    const canvas = new EventTarget();
    const unavailable = vi.fn();
    const stop = watchContextLoss(canvas, unavailable);
    const loss = new Event('webglcontextlost', { cancelable: true });
    canvas.dispatchEvent(loss);
    canvas.dispatchEvent(new Event('webglcontextlost'));
    expect(loss.defaultPrevented).toBe(true);
    expect(unavailable).toHaveBeenCalledTimes(1);
    stop();
    canvas.dispatchEvent(new Event('webglcontextlost'));
    expect(unavailable).toHaveBeenCalledTimes(1);
  });

  it('재시도한 캔버스만 감시하고 이전 캔버스의 뒤늦은 손실을 무시한다', () => {
    const oldCanvas = new EventTarget();
    const newCanvas = new EventTarget();
    const unavailable = vi.fn();
    const stop = watchContextLoss(oldCanvas, unavailable);
    stop();
    const stopNew = watchContextLoss(newCanvas, unavailable);
    oldCanvas.dispatchEvent(new Event('webglcontextlost'));
    expect(unavailable).not.toHaveBeenCalled();
    newCanvas.dispatchEvent(new Event('webglcontextlost'));
    expect(unavailable).toHaveBeenCalledTimes(1);
    stopNew();
  });
});
