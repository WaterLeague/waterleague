import { BufferGeometry, Float32BufferAttribute, ShapeUtils, Vector2 } from 'three';
import type { ParkingLot } from '../entity/parking';
import type { Terrain } from '../../terrain/entity/terrain';
import {
  drapeTriangle,
  drapeSegment,
  terrainMeshHeight,
} from '../../terrain/service/terrainDrapeService';

export function parkingGeometry(lots: ParkingLot[], terrain: Terrain | null) {
  const surfaces: number[] = [],
    lines: number[] = [],
    hits: number[] = [],
    hitEnds: number[] = [];
  for (const lot of lots) {
    for (const [polygons, output, lift] of [
      [lot.surfacePolygons, surfaces, 0.006],
      [lot.polygons, hits, 0.013],
    ] as const)
      for (const rings of polygons) {
        const vertices = rings.map((ring) => ring.slice(0, -1).map(([x, y]) => new Vector2(x, y)));
        const points = vertices.flat();
        for (const indices of ShapeUtils.triangulateShape(vertices[0], vertices.slice(1)))
          drapeTriangle(
            indices.map((i) => [points[i].x, points[i].y]) as [
              [number, number],
              [number, number],
              [number, number],
            ],
            terrain,
            (triangle) => {
              for (const p of triangle)
                output.push(p[0], terrainMeshHeight(terrain, p) + lift, -p[1]);
            }
          );
      }
    hitEnds.push(hits.length / 9);
    for (const slot of lot.displayOnly ? [] : lot.slots)
      for (let i = 1; i < slot.corners.length; i++)
        for (const segment of drapeSegment(slot.corners[i - 1], slot.corners[i], terrain))
          for (const p of segment) lines.push(p[0], terrainMeshHeight(terrain, p) + 0.01, -p[1]);
  }
  const surface = new BufferGeometry(),
    markings = new BufferGeometry(),
    hit = new BufferGeometry();
  surface.setAttribute('position', new Float32BufferAttribute(surfaces, 3));
  surface.computeVertexNormals();
  markings.setAttribute('position', new Float32BufferAttribute(lines, 3));
  hit.setAttribute('position', new Float32BufferAttribute(hits, 3));
  return { surface, markings, hit, hitEnds };
}
