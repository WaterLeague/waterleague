import type { StoragePlacement } from '../dto/storageDto';
import { validateCombinedDesign } from '../service/storageDesign';
import { useEffect, useRef, useState } from 'react';
import type { Account } from '../../account/entity/account';
import { ApiError } from '../../../shared/exception/ApiError';
import type { NetworkPlacement, WatershedCatalog, WatershedJob } from '../dto/watershedDto';
import {
  loadWatershedCatalog,
  listWatersheds,
  submitWatershed,
} from '../repository/watershedRepository';
import { designFingerprint } from '../service/watershedDesign';
const activeJob = (j: WatershedJob) => j.state === 'QUEUED' || j.state === 'RUNNING';
const userError = (e: unknown) =>
  e instanceof ApiError ? e.message : '관망 자료를 확인하지 못했습니다. 다시 조회해 주세요.';
export function useWatershed(account: Account | null, open: boolean) {
  const allowed = account?.role === 'MEMBER' && account.approvalStatus === 'APPROVED';
  const [catalog, setCatalog] = useState<WatershedCatalog | null>(null);
  const [jobs, setJobs] = useState<WatershedJob[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [drafts, setDrafts] = useState<NetworkPlacement[]>([]);
  const [storageDrafts, setStorageDrafts] = useState<StoragePlacement[]>([]);
  const [queryError, setQueryError] = useState('');
  const [submitError, setSubmitError] = useState('');
  const queryEpoch = useRef(0);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const submitting = useRef(false);
  const mounted = useRef(false);
  const post = useRef<AbortController | null>(null);
  const requestKeys = useRef(new Map<string, string>());
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      post.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (!open || !allowed) return;
    const abort = new AbortController();
    const epoch = ++queryEpoch.current;
    let timer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    let availableCatalog = catalog;
    const poll = async () => {
      if (abort.signal.aborted || epoch !== queryEpoch.current) return;
      if (document.hidden) {
        timer = setTimeout(poll, 3000);
        return;
      }
      setLoading(true);
      try {
        const signal = AbortSignal.any([abort.signal, AbortSignal.timeout(15000)]);
        const [nextCatalog, nextJobs] = await Promise.all([
          availableCatalog ?? loadWatershedCatalog(signal),
          listWatersheds(signal),
        ]);
        if (abort.signal.aborted || epoch !== queryEpoch.current) return;
        availableCatalog = nextCatalog;
        setCatalog(nextCatalog);
        setJobs(nextJobs);
        setQueryError('');
        attempts = 0;
        if (nextJobs.some(activeJob)) timer = setTimeout(poll, 3000);
      } catch (e) {
        if (abort.signal.aborted || epoch !== queryEpoch.current) return;
        setQueryError(userError(e));
        // 권한 실패의 자동 재시도는 멈추고 통신 실패만 간격을 두고 재시도한다.
        if (!(e instanceof ApiError && [401, 403].includes(e.status)) && ++attempts <= 3)
          timer = setTimeout(poll, attempts * 5000);
      } finally {
        if (!abort.signal.aborted && epoch === queryEpoch.current) setLoading(false);
      }
    };
    void poll();
    return () => {
      abort.abort();
      clearTimeout(timer);
    };
  }, [open, allowed, revision]);
  async function submit() {
    if (!allowed || !catalog || submitting.current) return;
    const invalid = validateCombinedDesign(catalog, drafts, storageDrafts);
    if (invalid) {
      setSubmitError(invalid);
      return;
    }
    const fingerprint = JSON.stringify([
      designFingerprint(catalog.catalogHash, drafts, catalog.costCatalogHash),
      catalog.storageCatalogHash,
      [...storageDrafts].sort((a, b) => a.id.localeCompare(b.id)),
    ]);
    let key = requestKeys.current.get(fingerprint);
    if (!key) {
      key = crypto.randomUUID();
      requestKeys.current.set(fingerprint, key);
    }
    submitting.current = true;
    setBusy(true);
    setSubmitError('');
    queryEpoch.current++;
    const abort = new AbortController();
    post.current = abort;
    try {
      const job = await submitWatershed(
        catalog.catalogHash,
        drafts,
        key,
        AbortSignal.any([abort.signal, AbortSignal.timeout(30000)]),
        drafts.length ? catalog.costCatalogHash : undefined,
        storageDrafts.length && catalog.storageCatalogHash
          ? { catalogHash: catalog.storageCatalogHash, placements: storageDrafts }
          : undefined
      );
      if (!mounted.current || abort.signal.aborted) return;
      setJobs((previous) => [job, ...previous.filter((v) => v.id !== job.id)].slice(0, 50));
      setSelectedId(job.id);
    } catch (e) {
      if (mounted.current && !abort.signal.aborted)
        setSubmitError(userError(e) + ' 동일 설계로 다시 요청하면 중복 계산을 방지합니다.');
    } finally {
      submitting.current = false;
      if (mounted.current) {
        setBusy(false);
        setRevision((v) => v + 1);
      }
    }
  }
  return {
    allowed,
    catalog,
    jobs,
    selectedId,
    selectJob: setSelectedId,
    job: jobs.find((j) => j.id === selectedId) ?? jobs[0] ?? null,
    drafts,
    setDrafts,
    storageDrafts,
    setStorageDrafts,
    error: submitError || queryError,
    busy,
    loading,
    submit,
    retry: () => {
      setSubmitError('');
      setCatalog(null);
      setRevision((v) => v + 1);
    },
  };
}
export type WatershedState = ReturnType<typeof useWatershed>;
