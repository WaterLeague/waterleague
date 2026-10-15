import { api } from '../../../shared/repository/apiClient';
import { mapComparison, mapSummaries } from '../mapper/comparisonMapper';
export const loadComparisons = async () => mapSummaries(await api('/comparisons'));
export const loadComparison = async (id: string) => mapComparison(await api('/comparisons/' + id));
export const createComparison = async (
  sourceVersionId: string,
  modelHashes: string[],
  requestKey: string
) => mapComparison(await api('/comparisons', 'POST', { sourceVersionId, modelHashes, requestKey }));
