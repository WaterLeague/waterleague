import { expect, it, vi } from 'vitest';
import { AccountSessionService } from './accountSessionService';
import { ApiError } from '../../../shared/exception/ApiError';
import type { Account } from '../entity/account';

const player = (id: string): Account => ({
  id,
  username: 'session_test',
  displayName: '시험 계정',
  role: 'MEMBER',
  memberType: 'PLAYER',
  approvalStatus: 'APPROVED',
  organizationId: null,
  districtId: '11200',
  affiliationType: 'AFFILIATED',
});
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

it('중복 최초 조회를 합치고 늦은 응답이 새 로그인·소속 선택을 덮어쓰지 않음', async () => {
  const response = deferred<Account>();
  const currentAccount = vi.fn(() => response.promise);
  const session = new AccountSessionService({ currentAccount, logout: vi.fn() });
  const first = session.load();
  expect(session.load()).toBe(first);
  session.setAccount(player('new'));
  response.resolve(player('old'));
  await first;
  expect(currentAccount).toHaveBeenCalledTimes(1);
  expect(session.getSnapshot().account?.id).toBe('new');
});

it('세션 만료 뒤 진행 중이던 조회로 계정이 복원되지 않음', async () => {
  const response = deferred<Account>();
  const session = new AccountSessionService({
    currentAccount: () => response.promise,
    logout: vi.fn(),
  });
  session.setAccount(player('old'));
  const loading = session.load();
  session.expire();
  response.resolve(player('old'));
  await loading;
  expect(session.getSnapshot().account).toBeNull();
  expect(session.getSnapshot().error).toContain('만료');
});

it('늦은 로그아웃 응답이 그동안 로그인한 새 계정을 지우지 않음', async () => {
  const response = deferred<void>();
  const logout = vi.fn(() => response.promise);
  const session = new AccountSessionService({ currentAccount: vi.fn(), logout });
  session.setAccount(player('old'));
  const first = session.signOut();
  await session.signOut();
  session.setAccount(player('new'));
  response.resolve();
  await first;
  expect(logout).toHaveBeenCalledTimes(1);
  expect(session.getSnapshot()).toMatchObject({ account: { id: 'new' }, busy: false, error: '' });
});

it('로그아웃 실패는 계정을 보존하고 내부 오류 원문을 표시하지 않음', async () => {
  const session = new AccountSessionService({
    currentAccount: vi.fn(),
    logout: vi.fn().mockRejectedValue(new Error('private internal failure')),
  });
  session.setAccount(player('old'));
  await session.signOut();
  expect(session.getSnapshot().account?.id).toBe('old');
  expect(session.getSnapshot().error).toBe(
    '계정 상태를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.'
  );
  expect(session.getSnapshot().busy).toBe(false);
});

it('비회원 401은 정상 초기 상태로 유지하고 다른 통신 실패는 숨기지 않음', async () => {
  const currentAccount = vi
    .fn()
    .mockRejectedValueOnce(new ApiError(401, 'AUTHENTICATION_REQUIRED', '인증 필요'))
    .mockRejectedValueOnce(new Error('internal transport'));
  const session = new AccountSessionService({ currentAccount, logout: vi.fn() });
  await session.load();
  expect(session.getSnapshot()).toMatchObject({ account: null, error: '' });
  await session.load();
  expect(session.getSnapshot().error).toContain('계정 상태를 확인하지 못했습니다');
});

it('계정 재조회가 401이면 기존 인증 상태를 제거함', async () => {
  const session = new AccountSessionService({
    currentAccount: vi
      .fn()
      .mockRejectedValue(new ApiError(401, 'AUTHENTICATION_REQUIRED', '인증 필요')),
    logout: vi.fn(),
  });
  session.setAccount(player('old'));
  await session.load();
  expect(session.getSnapshot().account).toBeNull();
  expect(session.getSnapshot().error).toContain('만료');
});

it('변경 전 스냅샷과 해제된 구독자를 변경하지 않음', () => {
  const session = new AccountSessionService({ currentAccount: vi.fn(), logout: vi.fn() });
  const before = session.getSnapshot(),
    listener = vi.fn();
  const unsubscribe = session.subscribe(listener);
  session.setAccount(player('new'));
  unsubscribe();
  session.setError('시험 오류');
  expect(before).toEqual({ account: null, error: '', busy: false });
  expect(listener).toHaveBeenCalledTimes(1);
});
