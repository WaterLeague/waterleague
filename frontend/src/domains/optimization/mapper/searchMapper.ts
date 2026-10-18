import type { Lab, Placement } from '../../game/entity/game';
import { searchDto, searchSummaryDto } from '../dto/searchDto';
import { SearchDataError } from '../exception/SearchDataError';
import type { ResearchSearch, SearchInput, SearchSummary } from '../entity/search';
import { searchFingerprint } from '../service/searchService';
function require(value: unknown): asserts value {
  if (!value) throw new SearchDataError();
}
const samePlacements = (a: Placement[], b: Placement[]) =>
  JSON.stringify(a.map((p) => [p.cellId, p.facilityType, p.areaM2]).sort()) ===
  JSON.stringify(b.map((p) => [p.cellId, p.facilityType, p.areaM2]).sort());
function checkSummary(d: SearchSummary) {
  require(new Set(d.arms.map((a) => a.arm)).size === 2);
  for (const a of d.arms)
    require(
      a.total === d.settings.candidatesPerArm &&
        a.queued + a.running + a.succeeded + a.failed + a.rejected === a.total &&
        (a.succeeded === 0) === (a.bestScore === null)
    );
  require(d.completeComparison === d.arms.every((a) => a.succeeded === a.total));
}
export function mapSearches(raw: unknown, modelHash: string): SearchSummary[] {
  const p = searchSummaryDto.array().max(50).safeParse(raw);
  require(p.success);
  require(new Set(p.data.map((d) => d.id)).size === p.data.length);
  p.data.forEach(checkSummary);
  return p.data.filter((d) => d.modelHash === modelHash);
}
function checkPlacement(list: Placement[], cost: number, lab: Lab, source: string) {
  require(
    list.length <= lab.model.maxPlacements &&
      new Set(list.map((p) => p.cellId)).size === list.length
  );
  let total = 0;
  for (const p of list) {
    const cell = lab.model.cells.find((c) => c.id === p.cellId);
    require(cell && cell.allowedTypes.includes(p.facilityType) && p.areaM2 <= cell.maxAreaM2);
    const unit = lab.model.unitCosts[p.facilityType];
    require(unit !== undefined && Number.isFinite(unit) && unit > 0);
    total += p.areaM2 * unit;
  }
  require(Math.abs(total - cost) < 0.0051);
  try {
    const parsed = comparisonPlacements(source);
    require(samePlacements(parsed, list));
  } catch {
    throw new SearchDataError();
  }
}
function comparisonPlacements(source: string): Placement[] {
  const parsed = searchDto.shape.candidates.element.shape.placements.safeParse(JSON.parse(source));
  require(parsed.success);
  return parsed.data;
}
export function mapSearch(
  raw: unknown,
  lab: Lab,
  organizationId: string,
  request?: SearchInput
): ResearchSearch {
  const parsed = searchDto.safeParse(raw);
  require(parsed.success);
  const d = parsed.data,
    g = d.generation,
    s = g.settings;
  require(
    d.modelHash === lab.modelHash &&
      g.modelHash === d.modelHash &&
      d.organizationId === organizationId &&
      s.budgetKrw <= lab.model.budget
  );
  checkSummary({ ...d, settings: s });
  require(
    g.requestedCount === g.sources.length &&
      new Set(g.sources.map((x) => x.sample.jobId)).size === g.requestedCount
  );
  const unique = new Map<string, (typeof g.sources)[number]>();
  for (const src of [...g.sources].sort((a, b) => a.sample.jobId.localeCompare(b.sample.jobId))) {
    require(src.sample.costKrw <= s.budgetKrw);
    checkPlacement(src.placements, src.sample.costKrw, lab, src.sample.placementsSource);
    const previous = unique.get(src.physicalHash);
    if (previous)
      require(
        previous.sample.score === src.sample.score &&
          previous.sample.costKrw === src.sample.costKrw &&
          samePlacements(previous.placements, src.placements)
      );
    else unique.set(src.physicalHash, src);
  }
  const ranked = [...unique.values()].sort((a, b) => b.sample.score - a.sample.score),
    cutoff = ranked[Math.min(s.topK, ranked.length) - 1].sample.score;
  const selected = ranked.filter((x) => x.sample.score >= cutoff),
    chosen = new Set(selected.map((x) => x.sample.jobId));
  require(
    g.uniquePhysicalCount === unique.size &&
      g.trainingCount === selected.length &&
      g.cutoffScore === cutoff &&
      d.sourceBestScore === ranked[0].sample.score
  );
  require(g.sources.every((x) => x.selected === chosen.has(x.sample.jobId)));
  if (request)
    require(
      searchFingerprint(request) ===
        searchFingerprint({ jobIds: g.sources.map((x) => x.sample.jobId), settings: s })
    );
  require(
    d.candidates.length === 2 * s.candidatesPerArm &&
      g.candidates.length === d.candidates.length &&
      new Set(d.candidates.map((c) => c.id)).size === d.candidates.length
  );
  require(new Set(g.candidates.map((c) => c.arm + ':' + c.ordinal)).size === g.candidates.length);
  require(new Set(d.candidates.map((c) => c.arm + ':' + c.ordinal)).size === d.candidates.length);
  for (const c of d.candidates) {
    const expected = g.candidates.find((x) => x.arm === c.arm && x.ordinal === c.ordinal);
    require(
      expected &&
        c.modelHash === d.modelHash &&
        c.ordinal <= s.candidatesPerArm &&
        c.inputHash === expected.inputHash &&
        c.costKrw === expected.costKrw &&
        c.costKrw <= s.budgetKrw &&
        samePlacements(c.placements, expected.placements)
    );
    checkPlacement(c.placements, c.costKrw, lab, expected.placementsSource);
    if (c.state === 'SUCCEEDED') {
      const r = c.result;
      require(
        r &&
          c.score !== null &&
          c.errorCode === null &&
          r.modelHash === c.modelHash &&
          r.inputHash === c.inputHash &&
          r.baseline.accountedDischargeM3 > 0.000001
      );
      const score =
        (100 * (r.baseline.accountedDischargeM3 - r.strategy.accountedDischargeM3)) /
        r.baseline.accountedDischargeM3;
      require(
        Math.abs(score - c.score) < 0.000000051 &&
          Math.abs(score - r.score) < 0.0000001 &&
          r.baseline.seriesM3s.length === lab.model.rainfall.depthsMm.length &&
          r.strategy.seriesM3s.length === r.baseline.seriesM3s.length
      );
    } else require(c.result === null && c.score === null);
  }
  for (const a of d.arms) {
    const rows = d.candidates.filter((c) => c.arm === a.arm),
      scores = rows.flatMap((c) => (c.score === null ? [] : [c.score]));
    require(
      rows.length === a.total &&
        new Set(rows.map((c) => c.inputHash)).size === rows.length &&
        a.bestScore === (scores.length ? Math.max(...scores) : null)
    );
    for (const [field, state] of [
      ['queued', 'QUEUED'],
      ['running', 'RUNNING'],
      ['succeeded', 'SUCCEEDED'],
      ['failed', 'FAILED'],
      ['rejected', 'REJECTED'],
    ] as const)
      require(a[field] === rows.filter((c) => c.state === state).length);
  }
  const pattern = new Set(d.candidates.filter((c) => c.arm === 'PATTERN').map((c) => c.inputHash));
  require(
    g.sharedCandidateCount ===
      d.candidates.filter((c) => c.arm === 'UNIFORM' && pattern.has(c.inputHash)).length
  );
  require(new Set(g.arms.map((a) => a.arm)).size === 2);
  for (const a of g.arms)
    require(
      a.attempts === s.candidatesPerArm + a.emptyRejected + a.sourceRejected + a.duplicateRejected
    );
  require(
    new Set(g.distributions.map((x) => x.cellId)).size === lab.model.cells.length &&
      g.distributions.length === lab.model.cells.length
  );
  for (const dist of g.distributions) {
    require(
      lab.model.cells.some((c) => c.id === dist.cellId) &&
        new Set(dist.options.map((o) => o.key)).size === dist.options.length &&
        dist.options.reduce((n, o) => n + o.observedCount, 0) === g.trainingCount
    );
    require(dist.options.every((o) => o.patternWeight === o.observedCount + 1));
  }
  return d;
}
