import { playbackSecond, rainfallFrame } from '../service/playbackService';
import { useEffect, useRef, useState } from 'react';
import { loadLab } from '../../game/repository/gameRepository';
import type { Lab, FacilityType } from '../../game/entity/game';
import type { DisasterCatalog } from '../../disaster/entity/disaster';
import { loadDisasters } from '../../disaster/repository/disasterRepository';
import type { Account } from '../../account/entity/account';
import type { SharedSite } from '../../installation/entity/installation';
import { siteKey } from '../../installation/entity/installation';
import { errorMessage } from '../../../shared/exception/ApiError';
import type { HistoricalDraft, HistoricalJob } from '../entity/historical';
import type { Budget } from '../../budget/dto/budgetDto';
import { designAccounting } from '../../budget/service/designAccounting';
import { loadHistorical, runHistorical } from '../repository/historicalRepository';

export function useHistorical(
  enabled: boolean,
  districtId: string,
  account: Account | null,
  budget: Budget | null,
  initialEventId: string
) {
  const [catalog, setCatalog] = useState<DisasterCatalog | null>(null);
  const eventId = initialEventId;
  const [lab, setLab] = useState<Lab | null>(null);
  const [drafts, setDrafts] = useState<HistoricalDraft[]>([]);
  const [job, setJob] = useState<HistoricalJob | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0),
    [playing, setPlaying] = useState(true);
  const [seekRevision, setSeekRevision] = useState(0);
  const seek = (second: number) => {
    setElapsedSeconds(second);
    setSeekRevision((v) => v + 1);
  };
  const [speed, setSpeed] = useState(1);
  const accountId = useRef(account?.id);
  const epoch = useRef(0);
  const pendingRequest = useRef<{ fingerprint: string; id: string } | null>(null);
  const event = catalog?.events.find((e) => e.id === eventId);
  const selectedRain = event?.regions.find((r) => r.districtId === districtId);
  const hash = selectedRain?.modelHash ?? '';
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
    setJob(null);
  }, [eventId]);
  useEffect(() => {
    epoch.current++;
    setJob(null);
    setBusy(false);
    setLab(null);
    if (!enabled || !hash) return;
    let active = true;
    loadLab(hash)
      .then((v) => {
        if (active) {
          setLab(v);
          setError('');
        }
      })
      .catch((e) => {
        if (active) setError(errorMessage(e));
      });
    return () => {
      active = false;
    };
  }, [enabled, hash]);
  useEffect(() => {
    if (accountId.current !== account?.id) {
      epoch.current++;
      setJob(null);
      setError('');
      setBusy(false);
      if (accountId.current) setDrafts([]);
      accountId.current = account?.id;
    }
  }, [account?.id]);
  useEffect(() => {
    if (!playing || !frameCount || !enabled) return;
    const beganAt = performance.now();
    const beganSecond = clockAnchor.current;
    const timer = setInterval(() => {
      setElapsedSeconds(playbackSecond(beganSecond, performance.now() - beganAt, speed, duration));
    }, 250);
    return () => clearInterval(timer);
  }, [enabled, playing, frameCount, speed, duration, seekRevision, eventId]);
  useEffect(() => {
    if (duration && elapsedSeconds >= duration) setPlaying(false);
  }, [elapsedSeconds, duration]);
  useEffect(() => {
    if (!job || !['QUEUED', 'RUNNING'].includes(job.state)) return;
    let active = true,
      pending = false;
    const timer = setInterval(async () => {
      if (pending || document.hidden) return;
      pending = true;
      try {
        const next = await loadHistorical(job.id);
        if (active) {
          setJob(next);
          if (next.state === 'FAILED' || next.state === 'REJECTED') pendingRequest.current = null;
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
  }, [job?.id, job?.state]);
  const current = drafts.filter((d) => d.site.districtId === districtId);
  const accounting = budget
    ? designAccounting(
        budget.accounting,
        drafts.map((d) => ({
          facilityType: d.facilityType,
          cost: d.areaM2 * d.site.unitCosts[d.facilityType],
        }))
      )
    : null;
  const remaining =
    (budget?.policy.personalLimitKrw ?? 0) -
    drafts.reduce((n, d) => n + d.areaM2 * d.site.unitCosts[d.facilityType], 0);
  function add(site: SharedSite, type: FacilityType, area: number) {
    if (
      !site.allowedTypes.includes(type) ||
      !Number.isFinite(area) ||
      area <= 0 ||
      area > site.maxAreaM2 ||
      area * site.unitCosts[type] > remaining ||
      area * site.unitCosts[type] >
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
      cost: area * site.unitCosts[type],
      installedAt: new Date().toISOString(),
      center: site.center,
      heightM: site.heightM,
    };
    epoch.current++;
    setBusy(false);
    setDrafts((d) => [...d, { site, facilityType: type, areaM2: area, marker }]);
    setJob(null);
    setError('');
  }
  function remove(id: string) {
    epoch.current++;
    setBusy(false);
    setDrafts((d) => d.filter((v) => v.marker.id !== id));
    setJob(null);
  }
  async function calculate(sensitivityCellId?: string) {
    if (!lab || !account || !current.length || busy) return;
    const generation = epoch.current;
    const fingerprint = JSON.stringify([
      districtId,
      lab.modelHash,
      current.map((d) => [d.site.cellId, d.facilityType, d.areaM2]),
      sensitivityCellId ?? null,
    ]);
    if (pendingRequest.current?.fingerprint !== fingerprint)
      pendingRequest.current = { fingerprint, id: crypto.randomUUID() };
    setBusy(true);
    setError('');
    try {
      const next = await runHistorical(
        districtId,
        lab.modelHash,
        current,
        pendingRequest.current.id,
        sensitivityCellId
      );
      if (generation === epoch.current) setJob(next);
    } catch (e) {
      if (generation === epoch.current) setError(errorMessage(e));
    } finally {
      if (generation === epoch.current) setBusy(false);
    }
  }
  const rainMm = selectedRain?.depthsMm[index] ?? 0;
  const at = timeline
    ? new Date(Date.parse(timeline.start) + elapsedSeconds * 1000).toISOString()
    : null;
  const currentResult =
    job?.modelHash === lab?.modelHash && job?.districtId === districtId ? job.result : null;
  return {
    lab,
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
