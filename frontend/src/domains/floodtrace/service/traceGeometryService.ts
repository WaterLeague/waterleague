import type { TraceTile } from '../entity/floodTrace';
import type { Terrain } from '../../terrain/entity/terrain';
import { drapeTriangle, terrainMeshHeight } from '../../terrain/service/terrainDrapeService';

export function tracePositions(
  tiles: Pick<TraceTile, 'triangleVertices'>[],
  terrain: Terrain | null
) {
  const positions: number[] = [];
  for (const tile of tiles) {
    for (let i = 0; i < tile.triangleVertices.length; i += 6) {
      const points = [0, 2, 4].map(
        (j) => [tile.triangleVertices[i + j], tile.triangleVertices[i + j + 1]] as [number, number]
      );
      drapeTriangle([points[0], points[1], points[2]], terrain, (triangle) => {
        if (positions.length >= 9000000) throw new Error('침수 기록 표시 한도 초과');
        // 기록에 없는 깊이를 만들지 않고 지형과의 겹침만 피한다.
        for (const p of triangle) positions.push(p[0], terrainMeshHeight(terrain, p) + 0.08, -p[1]);
      });
    }
  }
  return new Float32Array(positions);
}
