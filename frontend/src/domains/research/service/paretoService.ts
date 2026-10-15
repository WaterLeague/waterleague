import type { ResearchEntry } from '../entity/research';
export function isPareto(entry: ResearchEntry, all: ResearchEntry[]) {
  return !all.some(
    (other) =>
      other.cost <= entry.cost &&
      other.score >= entry.score &&
      (other.cost < entry.cost || other.score > entry.score)
  );
}
