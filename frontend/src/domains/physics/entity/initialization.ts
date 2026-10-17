import type { z } from 'zod';
import type { initializationDto } from '../dto/initializationDto';
export type InitializationEvidenceData = z.infer<typeof initializationDto>;
