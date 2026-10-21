import { placementAreaLimit } from '../../installation/service/placementAreaLimit';
import { unitCost } from '../../game/service/gameService';
import { playbackSecond, rainfallFrame } from '../service/playbackService';
import { useEffect, useRef, useState } from 'react';
import type { FacilityType } from '../../game/entity/game';
import type { DisasterCatalog } from '../../disaster/entity/disaster';
import { loadDisasters } from '../../disaster/repository/disasterRepository';
import type { Account } from '../../account/entity/account';
import type { SharedSite } from '../../installation/entity/installation';
import { siteKey } from '../../installation/entity/installation';
import { errorMessage } from '../../../shared/exception/ApiError';
import type { HistoricalJob } from '../entity/historical';
import type { Budget } from '../../budget/dto/budgetDto';
import { designAccounting } from '../../budget/service/designAccounting';
import {
  listHistorical,
  loadHistorical,
  runHistorical,
  runGuestHistorical,
} from '../repository/historicalRepository';
import {
  historicalScoreAt,
  matchesHistoricalDraft,
  restoreHistoricalJobs,
  nextHistoricalCalculation,
  historicalDistrictSignature,
  historicalFacilityStates,
} from '../service/temporalService';
import { useHistoricalSubmission } from './useHistoricalSubmission';
import { useHistoricalDesign } from './useHistoricalDesign';
import { useServerConnected } from '../../../shared/controller/serverConnectionContext';

export function useHistorical(
  enabled: boolean,
  districtId: string,
  account: Account | null,
  budget: Budget | null,
  initialEventId: string,
  competitionId?: string | null
) {
  const connected = useServerConnected();
  const [catalog, setCatalog] = useState<DisasterCatalog | null>(null);
  const eventId = initialEventId;
  const submission = useHistoricalSubmission(enabled, account?.id, eventId, competitionId);
  const design = useHistoricalDesign(enabled, eventId, account?.id, competitionId);
  const drafts = design.drafts;
  const [restoredJobs, setRestoredJobs] = useState('');
  const [jobs, setJobs] = useState<Record<string, HistoricalJob>>({});
  const [error, setError] = useState('');
  const [calculationErrors, setCalculationErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0),
    [playing, setPlaying] = useState(true);
  const [seekRevision, setSeekRevision] = useState(0);
  const seek = (second: number) => {
    if (!Number.isFinite(second)) return;
    setElapsedSeconds(Math.max(0, Math.min(duration, Math.floor(second))));
    setSeekRevision((v) => v + 1);
  };
  const [speed, setSpeed] = useState(1);
  const accountId = useRef(account?.id);
  const epoch = useRef(0);
  const pendingRequests = useRef(
    new Map<string, { fingerprint: string; id: string; parent?: string }>()
  );
  const autoAttempts = useRef(new Map<string, string>());
  const event = catalog?.events.find((e) => e.id === eventId);
  const selectedRain = event?.regions.find((r) => r.districtId === districtId);
  const hash = selectedRain?.modelHash ?? '';
  const job = jobs[hash] ?? null;
  const timeline = event?.regions[0];
  const frameCount = timeline?.depthsMm.length ?? 0;
  const duration = frameCount * 60;
  const index = rainfallFrame(elapsedSeconds, frameCount);
  const setIndex = (minute: number) => seek(minute * 60);
  const clockAnchor = useRef(0);
  clockAnchor.current = elapsedSeconds;
  const wetKey =
    event?.regions
      .filter((r) => (r.depthsMm[index] ?? 0) > 0)
      .map((r) => r.districtId)
      .join(',') ?? '';
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    loadDisasters()
      .then((c) => {
        if (active) {
          setCatalog(c);
        }
      })
      .catch((e) => {
        if (active) setError(errorMessage(e));
      });
    return () => {
      active = false;
    };
  }, [enabled]);
  useEffect(() => {
    setElapsedSeconds(0);
    setPlaying(true);
    setJobs({});
    setBusy(false);
    pendingRequests.current.clear();
    autoAttempts.current.clear();
    setCalculationErrors({});
    epoch.current++;
  }, [eventId, competitionId]);
  useEffect(() => {
    if (accountId.current !== account?.id) {
      epoch.current++;
      setJobs({});
      pendingRequests.current.clear();
      autoAttempts.current.clear();
      setCalculationErrors({});
      setError('');
      setBusy(false);
      accountId.current = account?.id;
    }
  }, [account?.id]);
  useEffect(() => {
    if (!design.restoreId || !timeline) return;
    setElapsedSeconds(Math.min(duration, design.restoredSecond));
    setSeekRevision((v) => v + 1);
    if (design.revision || drafts.length) setPlaying(false);
  }, [design.restoreId, timeline?.start]);
  const restoreKey = `${account?.id}/${eventId}/${design.restoreId}`;
  useEffect(() => {
    if (!enabled || !event || !design.restoreId) return;
    let active = true;
    const models = new Set(event.regions.map((r) => r.modelHash));
    void listHistorical(!account, competitionId)
      .then((values) => {
        if (!active) return;
        setJobs(restoreHistoricalJobs(values, models, drafts));
        setRestoredJobs(restoreKey);
      })
      .catch((e) => {
        if (active) setError(errorMessage(e));
      });
    return () => {
      active = false;
    };
  }, [enabled, account?.id, event, design.restoreId]);
  useEffect(() => {
    if (!playing || !frameCount || !enabled) return;
    if (!connected) {
      setPlaying(false);
      return;
    }
    const beganAt = performance.now();
    const beganSecond = clockAnchor.current;
    const timer = setInterval(() => {
      setElapsedSeconds(playbackSecond(beganSecond, performance.now() - beganAt, speed, duration));
    }, 250);
    return () => clearInterval(timer);
  }, [enabled, playing, frameCount, speed, duration, seekRevision, eventId, connected]);
  useEffect(() => {
    if (duration && elapsedSeconds >= duration) setPlaying(false);
  }, [elapsedSeconds, duration]);
  useEffect(() => {
    if (!enabled) return;
    const activeJobs = Object.values(jobs).filter((j) => ['QUEUED', 'RUNNING'].includes(j.state));
    if (!activeJobs.length) return;
    let active = true,
      pending = false;
    const timer = setInterval(async () => {
      if (pending || document.hidden) return;
      pending = true;
      try {
        const updated = await Promise.all(
          activeJobs.map((queued) => loadHistorical(queued.id, !account))
        );
        if (active) {
          setJobs((previous) => ({
            ...previous,
            ...Object.fromEntries(updated.map((next) => [next.modelHash, next])),
          }));
          for (const next of updated)
            if (next.state === 'FAILED' || next.state === 'REJECTED')
              pendingRequests.current.delete(next.districtId);
        }
      } catch (e) {
        if (active) setError(errorMessage(e));
      } finally {
        pending = false;
      }
    }, 1500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [enabled, account?.id, jobs]);
  const current = drafts.filter((d) => d.site.districtId === districtId);
  const accounting = budget
    ? designAccounting(
        budget.accounting,
        drafts.map((d) => ({
          facilityType: d.facilityType,
          cost: d.areaM2 * unitCost(d.site.unitCosts, d.facilityType),
        }))
      )
    : null;
  const remaining =
    (budget?.policy.personalLimitKrw ?? 0) -
    drafts.reduce((n, d) => n + d.areaM2 * unitCost(d.site.unitCosts, d.facilityType), 0);
  function add(site: SharedSite, type: FacilityType, area: number) {
    if (!design.ready) return;
    if (drafts.length >= 50) {
      setError('재해 설계는 여러 구를 합쳐 50곳까지 설치할 수 있습니다.');
      return;
    }
    if (!timeline || elapsedSeconds >= duration) {
      setError('재해 종료 이전 시각으로 이동한 뒤 설치해 주세요.');
      return;
    }
    if (
      !site.allowedTypes.includes(type) ||
      !Number.isFinite(area) ||
      area <= 0 ||
      area > placementAreaLimit(site, type) ||
      area * unitCost(site.unitCosts, type) > remaining ||
      area * unitCost(site.unitCosts, type) >
        (accounting?.facilities.find((f) => f.facilityType === type)?.availableKrw ?? 0) ||
      current.length >= 50
    ) {
      setError('시설·면적·예산·최대 50곳 조건을 확인해 주세요.');
      return;
    }
    if (drafts.some((d) => siteKey(d.site) === siteKey(site))) return;
    const marker = {
      id: crypto.randomUUID(),
      districtId: site.districtId,
      cellId: site.cellId,
      ownerId: account?.id ?? '00000000-0000-0000-0000-000000000000',
      ownerName: '내 연구 설계',
      facilityType: type,
      areaM2: area,
      cost: area * unitCost(site.unitCosts, type),
      installedAt: new Date(Date.parse(timeline.start) + elapsedSeconds * 1000).toISOString(),
      center: site.center,
      heightM: site.heightM,
    };
    design.replace([...drafts, { site, facilityType: type, areaM2: area, marker }], elapsedSeconds);
    setError('');
    return true;
  }
  function remove(id: string) {
    design.replace(
      drafts.filter((v) => v.marker.id !== id),
      elapsedSeconds
    );
  }
  async function calculate(
    sensitivityCellId?: string,
    targetDistrictId = districtId,
    pavementComparisonCellId?: string
  ) {
    const region = event?.regions.find((r) => r.districtId === targetDistrictId);
    const selected = drafts.filter((d) => d.site.districtId === targetDistrictId);
    if (
      !enabled ||
      !design.ready ||
      (account && !design.revision) ||
      restoredJobs !== restoreKey ||
      !region ||
      !selected.length ||
      busy
    )
      return;
    const generation = epoch.current;
    const fingerprint = JSON.stringify([
      design.revision,
      historicalDistrictSignature(region.modelHash, selected),
      sensitivityCellId ?? null,
      pavementComparisonCellId ?? null,
      !account
        ? drafts.map((d) => [
            d.site.districtId,
            d.site.cellId,
            d.site.modelHash,
            d.facilityType,
            d.areaM2,
            d.marker.installedAt,
          ])
        : null,
    ]);
    if (['FAILED', 'REJECTED'].includes(jobs[region.modelHash]?.state ?? ''))
      pendingRequests.current.delete(targetDistrictId);
    let pending = pendingRequests.current.get(targetDistrictId);
    if (pending?.fingerprint !== fingerprint) {
      pending = { fingerprint, id: crypto.randomUUID(), parent: jobs[region.modelHash]?.id };
      pendingRequests.current.set(targetDistrictId, pending);
    }
    setBusy(true);
    setError('');
    setCalculationErrors((v) => ({ ...v, [targetDistrictId]: '' }));
    try {
      const next = !account
        ? await runGuestHistorical(eventId, targetDistrictId, drafts, pending.id)
        : await runHistorical(
            targetDistrictId,
            region.modelHash,
            selected,
            pending.id,
            sensitivityCellId,
            pending.parent,
            { revision: design.revision, eventId },
            pavementComparisonCellId,
            competitionId
          );
      if (generation === epoch.current)
        setJobs((previous) => ({ ...previous, [next.modelHash]: next }));
    } catch (e) {
      if (generation === epoch.current) {
        setError(errorMessage(e));
        setCalculationErrors((v) => ({ ...v, [targetDistrictId]: errorMessage(e) }));
      }
    } finally {
      if (generation === epoch.current) setBusy(false);
    }
  }
  const rainMm = selectedRain?.depthsMm[index] ?? 0;
  const at = timeline
    ? new Date(Date.parse(timeline.start) + elapsedSeconds * 1000).toISOString()
    : null;
  const currentResult =
    job?.state === 'SUCCEEDED' &&
    job.modelHash === hash &&
    job.districtId === districtId &&
    matchesHistoricalDraft(job, current)
      ? job.result
      : null;
  const currentScore = currentResult && at ? historicalScoreAt(currentResult, at) : null;
  const calculateRef = useRef(calculate);
  calculateRef.current = calculate;
  useEffect(() => {
    if (!enabled || !design.ready || restoredJobs !== restoreKey || !event || busy) return;
    const next = nextHistoricalCalculation(event.regions, drafts, jobs, autoAttempts.current);
    if (!next) return;
    const timer = window.setTimeout(() => {
      autoAttempts.current.set(next.districtId, next.signature);
      void calculateRef.current(undefined, next.districtId);
    }, 750);
    return () => window.clearTimeout(timer);
  }, [enabled, account?.id, event, drafts, busy, jobs, design.ready, restoredJobs, restoreKey]);
  const facilityStates = historicalFacilityStates(event?.regions ?? [], drafts, jobs, at).map(
    (v) => ({ ...v, requestError: calculationErrors[v.draft.site.districtId] ?? '' })
  );
  return {
    design,
    submission,
    submit: async () => {
      if (design.ready && design.snapshotSha256 && drafts.length)
        await submission.submit({
          revision: design.revision,
          snapshotSha256: design.snapshotSha256,
        });
    },
    events: catalog?.events ?? [],
    event,
    eventId,
    selectedRain,
    frameCount,
    elapsedSeconds,
    setElapsedSeconds: seek,
    duration,
    wetKey,
    hash,
    drafts,
    current,
    remaining,
    budget,
    accounting,
    add,
    remove,
    job,
    currentResult,
    currentScore,
    facilityStates,
    calculationsReady: restoredJobs === restoreKey,
    error,
    busy,
    calculate,
    index,
    setIndex,
    playing,
    setPlaying,
    speed,
    setSpeed,
    rainMm,
    at,
  };
}
export type HistoricalState = ReturnType<typeof useHistorical>;
