import type { z } from 'zod';
import type { disasterCatalogDto } from '../dto/disasterDto';
export type DisasterCatalog = z.infer<typeof disasterCatalogDto>;
