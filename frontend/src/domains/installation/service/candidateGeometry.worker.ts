import { candidateGeometry } from './candidateGeometryService';
import type { GroundCandidate } from './candidateTilesService';
import type { Terrain } from '../../terrain/entity/terrain';
self.onmessage = ({ data }: { data: { rows: GroundCandidate[]; terrain: Terrain | null } }) => {
  try {
    const result = candidateGeometry(data.rows, data.terrain);
    self.postMessage(result, {
      transfer: [result.positions.buffer, result.masks.buffer, result.bounds.buffer],
    });
  } catch {
    self.postMessage({ failed: true });
  }
};
