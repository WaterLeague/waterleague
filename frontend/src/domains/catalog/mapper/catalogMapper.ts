import type { MapDto } from '../dto/catalogDto';
import type { CandidateMap } from '../entity/catalog';
export function toCandidateMap(snapshot: MapDto): CandidateMap {
  return {
    snapshot,
    buildings: snapshot.features.filter((f) => f.kind === 'building'),
    transports: snapshot.features.filter((f) => f.kind === 'transport'),
    roads: snapshot.features.filter((f) => f.kind === 'road'),
  };
}
