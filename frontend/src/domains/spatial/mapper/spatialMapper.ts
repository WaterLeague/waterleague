import { spatialDto } from '../dto/spatialDto';
import { SpatialError } from '../exception/SpatialError';
export function mapSpatial(value: unknown) {
  const parsed = spatialDto.safeParse(value);
  if (!parsed.success) throw new SpatialError();
  const buildings = parsed.data.buildings;
  if (
    new Set(buildings.map((b) => b.id)).size !== buildings.length ||
    buildings.reduce(
      (total, b) =>
        total + b.polygons.reduce((sum, p) => sum + p.reduce((n, r) => n + r.length, 0), 0),
      0
    ) > 50000
  )
    throw new SpatialError();
  return parsed.data;
}
