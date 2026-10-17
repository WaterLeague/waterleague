import type { z } from 'zod';
import type {
  infrastructureDto,
  infrastructureAssetDto,
  infrastructureSourceDto,
} from '../dto/infrastructureDto';
export type InfrastructureCatalog = z.infer<typeof infrastructureDto>;
export type InfrastructureAsset = z.infer<typeof infrastructureAssetDto>;
export type InfrastructureSource = z.infer<typeof infrastructureSourceDto>;
