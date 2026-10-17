import type { TraceTile } from '../entity/floodTrace';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainHeight } from '../../terrain/service/terrainService';

export function tracePositions(
  tiles: Pick<TraceTile, 'triangleVertices'>[],
  terrain: Terrain | null
) {
  const count = tiles.reduce((sum, tile) => sum + tile.triangleVertices.length / 2, 0);
  const positions = new Float32Array(count * 3);
  let offset = 0;
  for (const tile of tiles) {
    for (let i = 0; i < tile.triangleVertices.length; i += 2) {
      const x = tile.triangleVertices[i],
        y = tile.triangleVertices[i + 1];
      positions[offset++] = x;
      positions[offset++] = terrainHeight(terrain, [x, y]) + 2;
      positions[offset++] = -y;
    }
  }
  return positions;
}
