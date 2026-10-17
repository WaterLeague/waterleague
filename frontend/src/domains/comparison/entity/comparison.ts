import type { Version, Job } from '../../game/entity/game';
export interface ComparisonSummary {
  id: string;
  title: string;
  sourceVersionId: string;
  createdAt: string;
}
export interface RainfallComparison extends ComparisonSummary {
  sourceVersion: Version;
  jobs: (Job & { strategyId: string })[];
}
