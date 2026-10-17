import { expect, it, vi } from 'vitest';
import type { ResearchSearch, SearchInput, SearchSummary } from '../entity/search';
import { SearchSession, type SearchPort } from './SearchSession';
function deferred<T>() {
  let resolve!: (v: T) => void, reject!: (e: unknown) => void;
  const promise = new Promise<T>((a, b) => {
    resolve = a;
    reject = b;
  });
  return { promise, resolve, reject };
}
const detail = (id: string) => ({ id, candidates: [] }) as unknown as ResearchSearch;
const input: SearchInput = {
  jobIds: ['one', 'two'],
  settings: { topK: 2, budgetKrw: 100, seed: 17, candidatesPerArm: 1 },
};
function setup() {
  const port: SearchPort = {
      list: vi.fn(async () => []),
      get: vi.fn(async (id) => detail(id)),
      create: vi.fn(async () => detail('new')),
    },
    publish = vi.fn(),
    keys = vi.fn(() => crypto.randomUUID());
  return { port, publish, keys, c: new SearchSession(port, publish, keys) };
}
it('다른 기록 선택 후 늦게 도착한 이전 응답 무시', async () => {
  const { c, port } = setup(),
    old = deferred<ResearchSearch>();
  port.get = vi.fn((id) => (id === 'old' ? old.promise : Promise.resolve(detail(id))));
  const first = c.open('old');
  await c.open('new');
  old.resolve(detail('old'));
  await first;
  expect(c.state.detail?.id).toBe('new');
});
it('표본 변경·계정 해제 뒤 생성 응답과 오류의 화면 복원 차단', async () => {
  const { c, port, publish } = setup(),
    pending = deferred<ResearchSearch>();
  port.create = () => pending.promise;
  const request = c.create(input);
  c.invalidate();
  pending.resolve(detail('old'));
  await request;
  expect(c.state.detail).toBeNull();
  const late = deferred<ResearchSearch>();
  port.get = () => late.promise;
  const open = c.open('old');
  c.dispose();
  const count = publish.mock.calls.length;
  late.reject(new Error('이전 계정'));
  await open;
  expect(publish).toHaveBeenCalledTimes(count);
});
it('불명확한 생성 실패 재전송은 같은 키, 조건 변경과 성공 후 새 요청은 새 키', async () => {
  const { c, port, keys } = setup(),
    sent: string[] = [];
  let fail = true;
  port.create = async (_, key) => {
    sent.push(key);
    if (fail) throw new Error('연결 끊김');
    return detail('new');
  };
  await c.create(input);
  await c.create({ ...input, jobIds: [...input.jobIds].reverse() });
  expect(sent[0]).toBe(sent[1]);
  await c.create({ ...input, settings: { ...input.settings, seed: 18 } });
  expect(sent[2]).not.toBe(sent[1]);
  fail = false;
  await c.create(input);
  await c.create(input);
  expect(keys).toHaveBeenCalledTimes(4);
  expect(sent[3]).not.toBe(sent[4]);
});
it('생성 중 중복 버튼 요청 차단', async () => {
  const { c, port } = setup(),
    pending = deferred<ResearchSearch>();
  port.create = vi.fn(() => pending.promise);
  const first = c.create(input);
  await c.create(input);
  expect(port.create).toHaveBeenCalledTimes(1);
  pending.resolve(detail('new'));
  await first;
  expect(c.state.busy).toBe(false);
});
it('생성 성공 뒤 목록 조회 실패의 재시도에서 같은 키 유지', async () => {
  const { c, port, keys } = setup(),
    sent: string[] = [];
  port.create = async (_, key) => {
    sent.push(key);
    return detail('new');
  };
  port.list = vi.fn().mockRejectedValueOnce(new Error('목록 연결 끊김')).mockResolvedValueOnce([]);
  await c.create(input);
  expect(c.state.detail).toBeNull();
  await c.create(input);
  expect(sent[0]).toBe(sent[1]);
  expect(keys).toHaveBeenCalledTimes(1);
  expect(c.state.detail?.id).toBe('new');
});
it('포커스 권한 재조회 전에 상세 숨김과 철회 시 목록·선택·링크 제거', async () => {
  const { c, port } = setup();
  await c.open('private');
  const pending = deferred<ResearchSearch>();
  port.get = () => pending.promise;
  const refresh = c.refresh(true);
  expect(c.state.detail).toBeNull();
  pending.reject(new Error('동의 철회'));
  await refresh;
  expect(c.state).toMatchObject({ items: [], detail: null, selectedId: '', error: '동의 철회' });
});
it('숨김과 새 조회 후 이전 목록 응답의 재노출 차단', async () => {
  const { c, port } = setup(),
    old = deferred<SearchSummary[]>();
  port.list = vi.fn().mockReturnValueOnce(old.promise).mockResolvedValueOnce([]);
  const pending = c.refresh();
  c.conceal();
  await c.refresh(true);
  old.resolve([{ id: 'private' } as SearchSummary]);
  await pending;
  expect(c.state.items).toEqual([]);
});
