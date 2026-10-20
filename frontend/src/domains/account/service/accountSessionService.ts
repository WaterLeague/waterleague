import type { Account } from '../entity/account';
import * as gateway from '../repository/accountRepository';
import { ApiError } from '../../../shared/exception/ApiError';

type Snapshot = { account: Account | null; error: string; busy: boolean };
type Gateway = Pick<typeof gateway, 'currentAccount' | 'logout'>;
const unavailable = '계정 상태를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.';

export class AccountSessionService {
  private snapshot: Snapshot = { account: null, error: '', busy: false };
  private generation = 0;
  private pending: Promise<void> | null = null;
  private readonly listeners = new Set<() => void>();

  constructor(private readonly api: Gateway = gateway) {}

  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };
  private update(value: Partial<Snapshot>) {
    this.snapshot = { ...this.snapshot, ...value };
    this.listeners.forEach((listener) => listener());
  }
  setAccount = (account: Account | null) => {
    this.generation++;
    this.update({ account, error: '' });
  };
  setError = (error: string) => this.update({ error });
  expire = () => {
    this.generation++;
    this.update({
      account: null,
      error: this.snapshot.account
        ? '로그인이 만료되었습니다. 다시 로그인해 주세요.'
        : this.snapshot.error,
    });
  };
  load = (): Promise<void> => {
    if (this.pending) return this.pending;
    if (this.snapshot.busy) return Promise.resolve();
    const generation = this.generation;
    const request = Promise.resolve()
      .then(() => this.api.currentAccount())
      .then((account) => {
        // 늦은 최초 조회가 로그인·소속 변경·세션 만료를 덮어쓰지 않게 한다.
        if (generation === this.generation) this.setAccount(account);
      })
      .catch((error: unknown) => {
        if (generation !== this.generation) return;
        if (error instanceof ApiError && error.status === 401) {
          this.expire();
          return;
        }
        this.setError(error instanceof ApiError ? error.message : unavailable);
      })
      .finally(() => {
        if (this.pending === request) this.pending = null;
      });
    this.pending = request;
    return request;
  };
  signOut = async () => {
    if (this.snapshot.busy) return;
    const generation = ++this.generation;
    this.update({ busy: true, error: '' });
    try {
      await this.api.logout();
      if (generation === this.generation) this.setAccount(null);
    } catch (error: unknown) {
      if (generation === this.generation)
        this.setError(error instanceof ApiError ? error.message : unavailable);
    } finally {
      this.update({ busy: false });
    }
  };
}
