import type { z } from 'zod';
import type { searchDto, searchSettingsDto, searchSummaryDto } from '../dto/searchDto';
export type SearchSettings = z.infer<typeof searchSettingsDto>;
export type ResearchSearch = z.infer<typeof searchDto>;
export type SearchSummary = z.infer<typeof searchSummaryDto>;
export type SearchCandidate = ResearchSearch['candidates'][number];
export type SearchArm = SearchCandidate['arm'];
export interface SearchInput {
  jobIds: string[];
  settings: SearchSettings;
}
