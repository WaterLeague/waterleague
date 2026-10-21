import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ServerConnectionService } from './ServerConnectionService';

let service: ServerConnectionService;
beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  service?.stop();
  vi.useRealTimers();
});

describe('서버 연결 상태', () => {
  it('첫 접속, 사용 중 단절, 자동 복구와 중복 요청 방지', async () => {
    const probe = vi
      .fn()
      .mockResolvedValueOnce(true)
      .mockResolvedValueOnce(false)
      .mockResolvedValue(true);
    service = new ServerConnectionService(probe, () => true);
    service.start();
    const request = service.check();
    expect(service.check()).toBe(request);
    await request;
    expect(service.getSnapshot()).toEqual({ status: 'connected', checking: false });
    await vi.advanceTimersByTimeAsync(15_000);
    expect(service.getSnapshot().status).toBe('disconnected');
    await vi.advanceTimersByTimeAsync(10_000);
    expect(service.getSnapshot().status).toBe('connected');
    expect(probe).toHaveBeenCalledTimes(3);
  });

  it('응답이 끝나지 않으면 8초 후 중단하고 수동 재연결', async () => {
    let signal!: AbortSignal;
    const probe = vi
      .fn()
      .mockImplementationOnce((value: AbortSignal) => {
        signal = value;
        return new Promise<boolean>(() => {});
      })
      .mockResolvedValue(true);
    service = new ServerConnectionService(probe, () => true);
    service.start();
    await vi.advanceTimersByTimeAsync(8_000);
    expect(signal.aborted).toBe(true);
    expect(service.getSnapshot()).toEqual({ status: 'disconnected', checking: false });
    const retry = service.check();
    expect(service.getSnapshot()).toEqual({ status: 'disconnected', checking: true });
    await retry;
    expect(service.getSnapshot().status).toBe('connected');
  });

  it('중지 후 도착한 이전 응답은 재시작한 상태에 반영하지 않음', async () => {
    let finish!: (value: boolean) => void;
    const probe = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise<boolean>((resolve) => {
            finish = resolve;
          })
      )
      .mockResolvedValue(true);
    service = new ServerConnectionService(probe, () => true);
    service.start();
    const old = service.check();
    await vi.advanceTimersByTimeAsync(0);
    service.stop();
    service.start();
    await service.check();
    finish(false);
    await old;
    expect(service.getSnapshot().status).toBe('connected');
    service.stop();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(probe).toHaveBeenCalledTimes(2);
  });

  it('숨긴 탭에서는 주기 조회를 쉬고 통신 실패 알림을 합침', async () => {
    let visible = false;
    const probe = vi.fn().mockResolvedValue(true);
    service = new ServerConnectionService(probe, () => visible);
    service.start();
    await service.check();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(probe).toHaveBeenCalledTimes(1);
    visible = true;
    service.checkAfterFailure();
    service.checkAfterFailure();
    await service.check();
    service.checkAfterFailure();
    expect(probe).toHaveBeenCalledTimes(2);
    expect(service.getSnapshot().status).toBe('connected');
  });

  it('조회 예외의 내부 내용을 상태에 노출하지 않음', async () => {
    service = new ServerConnectionService(
      async () => {
        throw new Error('private server detail');
      },
      () => true
    );
    const listener = vi.fn();
    const unsubscribe = service.subscribe(listener);
    service.start();
    await service.check();
    expect(service.getSnapshot()).toEqual({ status: 'disconnected', checking: false });
    expect(listener).toHaveBeenCalledOnce();
    unsubscribe();
  });
});
