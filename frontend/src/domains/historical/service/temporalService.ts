import type { HistoricalDraft, HistoricalJob, HistoricalScoreFrame } from '../entity/historical';

export const temporalPolicy = 'INSTALLATION_TIME_EXPERIMENT_V1' as const;

export function matchesHistoricalDraft(job: HistoricalJob | null, drafts: HistoricalDraft[]) {
  return (
    !!job &&
    job.placements.length === drafts.length &&
    drafts.every((d) =>
      job.placements.some(
        (p) =>
          p.districtId === d.site.districtId &&
          p.cellId === d.site.cellId &&
          p.facilityType === d.facilityType &&
          p.areaM2 === d.areaM2 &&
          p.siteModelHash === d.site.modelHash &&
          p.temporalPolicy === temporalPolicy &&
          Date.parse(p.installedAt ?? '') === Date.parse(d.marker.installedAt)
      )
    )
  );
}

export function restoreHistoricalJobs(
  values: HistoricalJob[],
  models: ReadonlySet<string>,
  drafts: HistoricalDraft[]
) {
  const restored: Record<string, HistoricalJob> = {};
  for (const value of values) {
    if (
      !models.has(value.modelHash) ||
      !value.placements.length ||
      !value.placements.every((p) => p.temporalPolicy === temporalPolicy)
    )
      continue;
    const current = drafts.filter((d) => d.site.districtId === value.districtId);
    const previous = restored[value.modelHash];
    if (
      !previous ||
      (!matchesHistoricalDraft(previous, current) && matchesHistoricalDraft(value, current))
    )
      restored[value.modelHash] = value;
  }
  return restored;
}

export function scoreAt(frames: HistoricalScoreFrame[], at: string): HistoricalScoreFrame | null {
  const instant = Date.parse(at);
  let found: HistoricalScoreFrame | null = null;
  for (const frame of frames) {
    if (Date.parse(frame.at) <= instant && (!found || Date.parse(frame.at) > Date.parse(found.at)))
      found = frame;
  }
  return found;
}

export function historicalScoreAt(result: NonNullable<HistoricalJob['result']>, at: string) {
  if (result.temporalPolicy !== temporalPolicy) return null;
  const values = (result.facilities ?? []).map((f) => {
    if (!f.installedAt || !f.frames) return null;
    if (Date.parse(at) < Date.parse(f.installedAt))
      return {
        at,
        differenceM3: 0,
        baselineAccountedM3: 0,
        designAccountedM3: 0,
      };
    return scoreAt(f.frames, at);
  });
  if (!values.length || values.some((f) => !f)) return null;
  return values.reduce<HistoricalScoreFrame>(
    (sum, frame) => ({
      at: Date.parse(frame!.at) < Date.parse(sum.at) ? frame!.at : sum.at,
      differenceM3: sum.differenceM3 + frame!.differenceM3,
      baselineAccountedM3: sum.baselineAccountedM3 + frame!.baselineAccountedM3,
      designAccountedM3: sum.designAccountedM3 + frame!.designAccountedM3,
    }),
    { at, differenceM3: 0, baselineAccountedM3: 0, designAccountedM3: 0 }
  );
}

export function historicalDistrictSignature(modelHash: string, drafts: HistoricalDraft[]) {
  return JSON.stringify([
    modelHash,
    [...drafts]
      .sort((a, b) => a.site.cellId.localeCompare(b.site.cellId))
      .map((d) => [
        d.site.cellId,
        d.site.modelHash,
        d.facilityType,
        d.areaM2,
        d.marker.installedAt,
      ]),
  ]);
}
type Region = { districtId: string; modelHash: string };
export function nextHistoricalCalculation(
  regions: Region[],
  drafts: HistoricalDraft[],
  jobs: Record<string, HistoricalJob>,
  attempts: ReadonlyMap<string, string>
) {
  if (Object.values(jobs).some((j) => ['QUEUED', 'RUNNING'].includes(j.state))) return null;
  for (const region of [...regions].sort((a, b) => a.districtId.localeCompare(b.districtId))) {
    const selected = drafts.filter((d) => d.site.districtId === region.districtId);
    if (!selected.length || matchesHistoricalDraft(jobs[region.modelHash] ?? null, selected))
      continue;
    const signature = historicalDistrictSignature(region.modelHash, selected);
    if (attempts.get(region.districtId) !== signature) return { ...region, signature };
  }
  return null;
}
export function historicalFacilityStates(
  regions: Region[],
  drafts: HistoricalDraft[],
  jobs: Record<string, HistoricalJob>,
  at: string | null
) {
  return drafts.map((draft) => {
    const region = regions.find((r) => r.districtId === draft.site.districtId);
    const candidate = region ? jobs[region.modelHash] : undefined;
    const matching = matchesHistoricalDraft(
      candidate ?? null,
      drafts.filter((d) => d.site.districtId === draft.site.districtId)
    );
    const job = matching ? candidate : undefined;
    const result =
      job?.state === 'SUCCEEDED'
        ? job.result?.facilities?.find((f) => f.cellId === draft.site.cellId)
        : undefined;
    return {
      draft,
      state: job?.state,
      jobId: job?.id,
      before: !!at && Date.parse(at) < Date.parse(draft.marker.installedAt),
      score: at && result?.frames ? scoreAt(result.frames, at) : null,
    };
  });
}
