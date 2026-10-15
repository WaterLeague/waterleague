import type { z } from 'zod';
import type { spatialDto } from '../dto/spatialDto';
export type SpatialReference = z.infer<typeof spatialDto>;
