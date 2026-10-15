import { labDto, rainfallCatalogDto } from '../dto/labDto';
import { GameDataError } from '../exception/GameDataError';
import type { Lab, RainfallCatalog } from '../entity/game';
export function mapLab(value: unknown): Lab {
  const parsed = labDto.safeParse(value);
  if (!parsed.success) throw new GameDataError();
  const lab = parsed.data,
    rain = lab.model.rainfall,
    cells = lab.model.cells;
  if (
    new Set(cells.map((c) => c.id)).size !== cells.length ||
    cells.some((c) => c.maxAreaM2 > c.areaM2)
  )
    throw new GameDataError();
  const duration = (Date.parse(rain.end) - Date.parse(rain.start)) / 1000;
  if (
    duration !== rain.depthsMm.length * rain.intervalSeconds ||
    Math.abs(rain.depthsMm.reduce((a, b) => a + b, 0) - rain.totalDepthMm) > 0.001
  )
    throw new GameDataError();
  return lab;
}

export function mapRainfallCatalog(value: unknown): RainfallCatalog {
  const parsed = rainfallCatalogDto.safeParse(value);
  if (!parsed.success) throw new GameDataError();
  const result = parsed.data;
  if (
    new Set(result.models.map((m) => m.modelHash)).size !== result.models.length ||
    !result.models.some((m) => m.modelHash === result.defaultModelHash)
  )
    throw new GameDataError();
  return result;
}
