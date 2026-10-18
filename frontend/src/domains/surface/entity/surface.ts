import type { z } from 'zod';
import type { surfaceCatalogDto, surfaceFrameDto } from '../dto/surfaceDto';
export type SurfaceCatalog = z.infer<typeof surfaceCatalogDto>;
export type SurfaceFrame = z.infer<typeof surfaceFrameDto>;
export type SurfaceMetric = 'depth' | 'speed';
export type SurfaceSource = {
  kind: 'historical' | 'installation' | 'own-record' | 'research-record';
  id: string;
};
