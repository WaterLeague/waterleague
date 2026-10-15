import { useState, useEffect, useCallback, useRef, useReducer } from 'react';
import * as repo from '../repository/gameRepository';
import * as auth from '../../account/repository/accountRepository';
import type { Account } from '../../account/entity/account';
import type {
  Lab,
  Placement,
  Version,
  Job,
  StrategySummary,
  RainfallCatalog,
} from '../entity/game';
import { errorMessage } from '../../../shared/exception/ApiError';
import { onSessionExpired } from '../../../shared/repository/apiClient';
import { placementHistoryReducer } from '../service/placementHistoryService';

export function useGame() {
  const [lab, setLab] = useState<Lab | null>(null);
  const [rainfallCatalog, setRainfallCatalog] = useState<RainfallCatalog | null>(null);
  const modelRequest = useRef(0);
  const [account, setAccount] = useState<Account | null>(null);
  const [history, dispatchHistory] = useReducer(placementHistoryReducer, {
    past: [],
    present: [],
    future: [],
  });
  const placements = history.present;
  const [title, setTitle] = useState('성수의 빗물 설계');
  const [note, setNote] = useState('');
  const [version, setVersion] = useState<Version | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [strategies, setStrategies] = useState<StrategySummary[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const owner = useRef<string | undefined>(undefined);
  owner.current = account?.id;

  useEffect(
    () =>
      onSessionExpired(() => {
        const hadAccount = !!owner.current;
        owner.current = undefined;
        setAccount(null);
        setStrategies([]);
        setVersion(null);
        setJob(null);
        if (hadAccount) setError('로그인이 만료되었습니다. 다시 로그인해 주세요.');
      }),
    []
  );

  useEffect(() => {
    let alive = true;
    repo
      .loadLab()
      .then((v) => {
        if (alive) setLab(v);
      })
      .catch((e) => {
        if (alive) setError(errorMessage(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    repo
      .loadRainfallCatalog()
      .then((v) => {
        if (alive) setRainfallCatalog(v);
      })
      .catch((e) => {
        if (alive) setError(errorMessage(e));
      });
    auth
      .currentAccount()
      .then((v) => {
        if (alive && !owner.current) setAccount(v);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    const id = owner.current;
    const rows = await repo.loadStrategies();
    if (id === owner.current) setStrategies(rows);
  }, []);

  useEffect(() => {
    let alive = true;
    setStrategies([]);
    setJob(null);
    setVersion(null);
    if (account?.role === 'MEMBER') {
      repo
        .loadStrategies()
        .then((rows) => {
          if (alive) setStrategies(rows);
        })
        .catch((e) => {
          if (alive) setError(errorMessage(e));
        });
    }
    return () => {
      alive = false;
    };
  }, [account]);

  useEffect(() => {
    if (!job || !['QUEUED', 'RUNNING'].includes(job.state)) return;
    let alive = true;
    const id = window.setInterval(() => {
      repo
        .loadJob(job.id)
        .then((j) => {
          if (alive) setJob(j);
        })
        .catch((e) => {
          if (alive) setError(errorMessage(e));
        });
    }, 2000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [job]);

  function change(next: Placement[]) {
    dispatchHistory({ type: 'CHANGE', placements: next });
    setNotice('');
  }
  function undo() {
    dispatchHistory({ type: 'UNDO' });
    setNotice('');
  }
  function redo() {
    dispatchHistory({ type: 'REDO' });
    setNotice('');
  }
  async function action<T>(work: () => Promise<T>): Promise<T | undefined> {
    const id = owner.current;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      return await work();
    } catch (e) {
      if (id === owner.current) setError(errorMessage(e));
      return undefined;
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    if (!lab || !account) return;
    const saved = await repo.saveStrategy(
      version?.strategyId ?? null,
      title,
      lab.modelHash,
      placements,
      note,
      version?.revision ?? 0
    );
    if (account.id !== owner.current) return;
    setVersion(saved);
    await refresh();
    setNotice('설계 버전 ' + saved.revision + ' 저장 완료');
    return saved;
  }
  async function run() {
    await action(async () => {
      const id = owner.current;
      const saved = await save();
      if (saved) {
        const j = await repo.enqueue(saved.id, crypto.randomUUID());
        if (id !== owner.current) return;
        setJob(j);
        setNotice('계산 요청 완료. 화면을 나가도 서버에서 계속 계산합니다.');
      }
    });
  }
  async function open(id: string) {
    await action(async () => {
      const accountId = owner.current;
      const [s, jobs] = await Promise.all([repo.loadStrategy(id), repo.loadJobs()]);
      if (accountId !== owner.current) return;
      const v = s.versions[s.versions.length - 1];
      const nextLab = v.modelHash === lab?.modelHash ? lab : await repo.loadLab(v.modelHash);
      if (accountId !== owner.current) return;
      setLab(nextLab);
      setVersion(v);
      setTitle(s.title);
      setNote(v.designNote);
      dispatchHistory({ type: 'RESET', placements: v.placements });
      setJob(jobs.find((j) => j.versionId === v.id && j.modelHash === nextLab.modelHash) ?? null);
      setNotice('저장된 설계 불러오기 완료');
    });
  }
  async function selectModel(hash: string, copy = true) {
    const request = ++modelRequest.current,
      id = owner.current;
    const next = await repo.loadLab(hash);
    if (request !== modelRequest.current || id !== owner.current) return undefined;
    const compatible =
      lab &&
      JSON.stringify(lab.model.cells) === JSON.stringify(next.model.cells) &&
      JSON.stringify(lab.model.unitCosts) === JSON.stringify(next.model.unitCosts) &&
      lab.model.budget === next.model.budget;
    setLab(next);
    setVersion(null);
    setJob(null);
    dispatchHistory(
      copy && compatible ? { type: 'CLEAR_HISTORY' } : { type: 'RESET', placements: [] }
    );
    setNotice(
      copy && compatible
        ? '배치를 새 강우 조건으로 복사했습니다. 저장·계산 결과는 조건별로 남습니다.'
        : '새 강우 조건을 선택했습니다.'
    );
    return next;
  }
  function newDesign() {
    setVersion(null);
    dispatchHistory({ type: 'RESET', placements: [] });
    setTitle('새 빗물 설계');
    setNote('');
    setJob(null);
  }
  return {
    lab,
    rainfallCatalog,
    selectModel,
    account,
    setAccount,
    placements,
    change,
    undo,
    redo,
    canUndo: history.past.length > 0,
    canRedo: history.future.length > 0,
    title,
    setTitle,
    note,
    setNote,
    version,
    job,
    strategies,
    error,
    setError,
    notice,
    setNotice,
    busy,
    loading,
    action,
    save,
    run,
    open,
    newDesign,
  };
}
