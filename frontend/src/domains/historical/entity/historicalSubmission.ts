import type { z } from 'zod';
import type { historicalBoardDto, historicalSubmissionDto } from '../dto/submissionDto';
export type HistoricalSubmission = z.infer<typeof historicalSubmissionDto>;
export type HistoricalBoard = z.infer<typeof historicalBoardDto>;
