import { useState, useEffect, useCallback, useRef } from 'react';
import * as repo from '../repository/gameRepository';
import * as auth from '../../account/repository/accountRepository';
import type { Account } from '../../account/entity/account';
import type { Lab, Placement, Version, Job, StrategySummary } from '../entity/game';
import { errorMessage } from '../../../shared/exception/ApiError';

export function useGame() {
  const [lab, setLab] = useState<Lab | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [placements, setPlacements] = useState<Placement[]>([]);
  const [undoStack, setUndo] = useState<Placement[][]>([]);
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
    if (account) {
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
    setUndo((old) => [...old.slice(-49), placements]);
    setPlacements(next);
    setNotice('');
  }
  function undo() {
    if (undoStack.length) {
      setPlacements(undoStack[undoStack.length - 1]);
      setUndo((s) => s.slice(0, -1));
    }
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
      // 다른 모델·설계의 결과를 현재 편집안의 계산 결과로 표시하지 않는다.
      if (v.modelHash !== lab?.modelHash)
        throw new Error('이 설계는 이전 실험 조건입니다. 새 설계에서 다시 배치해 주세요.');
      setVersion(v);
      setTitle(s.title);
      setNote(v.designNote);
      setPlacements(v.placements);
      setUndo([]);
      setJob(jobs.find((j) => j.versionId === v.id && j.modelHash === lab.modelHash) ?? null);
      setNotice('저장된 설계 불러오기 완료');
    });
  }
  function newDesign() {
    setVersion(null);
    setPlacements([]);
    setUndo([]);
    setTitle('새 빗물 설계');
    setNote('');
    setJob(null);
  }
  return {
    lab,
    account,
    setAccount,
    placements,
    change,
    undo,
    canUndo: undoStack.length > 0,
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
