import type { z } from 'zod';
import type { liveRainfallDto } from '../dto/liveRainfallDto';
export type LiveRainfall = z.infer<typeof liveRainfallDto>;
