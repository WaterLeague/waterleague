import type { z } from 'zod';
import type {
  traceCatalogDto,
  traceEventDto,
  traceTileDto,
  traceTileIndexDto,
} from '../dto/floodTraceDto';
export type TraceCatalog = z.infer<typeof traceCatalogDto>['catalog'];
export type TraceEvent = z.infer<typeof traceEventDto>;
export type TraceTile = z.infer<typeof traceTileDto>;
export type TraceTileIndex = z.infer<typeof traceTileIndexDto>;
