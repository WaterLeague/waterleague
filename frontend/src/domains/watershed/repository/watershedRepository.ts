import type { CisternPlacement } from '../dto/cisternDto';
import type { PumpPlacement } from '../dto/pumpDto';
import type { ConduitPlacement } from '../dto/conduitDto';
import type { StoragePlacement } from '../dto/storageDto';
import { z } from 'zod';
import { api } from '../../../shared/repository/apiClient';
import { watershedCatalogDto, watershedJobDto, type NetworkPlacement } from '../dto/watershedDto';
export const loadWatershedCatalog = async (signal?: AbortSignal) =>
  watershedCatalogDto.parse(await api('/watersheds/catalog', 'GET', undefined, signal));
export const listWatersheds = async (signal?: AbortSignal) =>
  z
    .array(watershedJobDto)
    .max(50)
    .parse(await api('/watersheds', 'GET', undefined, signal));
export const submitWatershed = async (
  catalogHash: string,
  placements: NetworkPlacement[],
  requestKey: string,
  signal?: AbortSignal,
  costCatalogHash?: string,
  storage?: { catalogHash: string; placements: StoragePlacement[] },
  conduits?: { catalogHash: string; placements: ConduitPlacement[] },
  cisternCostCatalogHash?: string,
  pumps?: { catalogHash: string; placements: PumpPlacement[] },
  cistern?: { catalogHash: string; placement: CisternPlacement }
) =>
  watershedJobDto.parse(
    await api(
      '/watersheds',
      'POST',
      {
        catalogHash,
        placements,
        requestKey,
        costCatalogHash,
        storage,
        conduits,
        cisternCostCatalogHash,
        pumps,
        cistern,
      },
      signal
    )
  );
