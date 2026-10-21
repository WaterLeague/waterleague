import { checkConnectionHealth } from '../repository/connectionHealthRepository';

type ConnectionSnapshot = {
  status: 'checking' | 'connected' | 'disconnected';
  checking: boolean;
};

export class ServerConnectionService {
  private snapshot: ConnectionSnapshot = { status: 'checking', checking: true };
  private listeners = new Set<() => void>();
  private running = false;
  private generation = 0;
  private pending: Promise<void> | undefined;
  private controller: AbortController | undefined;
  private timeout: ReturnType<typeof setTimeout> | undefined;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private lastCheck = -Infinity;

  constructor(
    private readonly probe = checkConnectionHealth,
    private readonly visible = () => document.visibilityState !== 'hidden'
  ) {}

  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  start() {
    this.running = true;
    void this.check();
  }

  stop() {
    this.running = false;
    this.generation++;
    clearTimeout(this.timer);
    clearTimeout(this.timeout);
    this.controller?.abort();
    this.pending = undefined;
  }

  checkAfterFailure = () => {
    // 같은 장애에서 여러 요청이 실패해도 상태 확인은 한 번만 수행한다.
    if (Date.now() - this.lastCheck >= 2_000) void this.check();
  };

  check = (): Promise<void> => {
    if (!this.running) return Promise.resolve();
    if (this.pending) return this.pending;
    clearTimeout(this.timer);
    const generation = this.generation;
    const controller = new AbortController();
    this.controller = controller;
    this.lastCheck = Date.now();
    this.update({ ...this.snapshot, checking: true });
    // 응답 본문이 멈춘 경우도 제한 시간 안에 연결 실패로 처리한다.
    const timeout = new Promise<boolean>((resolve) => {
      this.timeout = setTimeout(() => {
        controller.abort();
        resolve(false);
      }, 8_000);
    });
    const probe = Promise.resolve()
      .then(() => this.probe(controller.signal))
      .catch(() => false);
    const pending = Promise.race([probe, timeout])
      .then((connected) => {
        if (this.running && generation === this.generation)
          this.update({ status: connected ? 'connected' : 'disconnected', checking: false });
      })
      .finally(() => {
        if (generation !== this.generation) return;
        clearTimeout(this.timeout);
        this.pending = undefined;
        this.schedule();
      });
    this.pending = pending;
    return pending;
  };

  private schedule() {
    if (!this.running) return;
    this.timer = setTimeout(
      () => {
        if (this.visible()) void this.check();
        else this.schedule();
      },
      this.snapshot.status === 'connected' ? 15_000 : 10_000
    );
  }

  private update(snapshot: ConnectionSnapshot) {
    if (snapshot.status === this.snapshot.status && snapshot.checking === this.snapshot.checking)
      return;
    this.snapshot = snapshot;
    this.listeners.forEach((listener) => listener());
  }
}
