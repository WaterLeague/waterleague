import { api } from '../../../shared/repository/apiClient';
import {
  mapResearchComparison,
  mapResearchComparisons,
  mapPatternAnalysis,
} from '../mapper/analysisMapper';
export const loadComparisons = async () =>
  mapResearchComparisons(await api('/research/comparisons'));
export const loadComparison = async (id: string) =>
  mapResearchComparison(await api('/research/comparisons/' + id));
export const createComparison = async (
  sourceJobId: string,
  modelHashes: string[],
  requestKey: string
) =>
  mapResearchComparison(
    await api('/research/comparisons', 'POST', { sourceJobId, modelHashes, requestKey })
  );
export const analyzePatterns = async (jobIds: string[], topK: number) =>
  mapPatternAnalysis(await api('/research/patterns', 'POST', { jobIds, topK }));
