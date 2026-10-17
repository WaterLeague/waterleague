import * as THREE from 'three';
import type { Building } from '../entity/catalog';
export type MapPolygons = [number, number][][][];

export function buildingPolygons(building: Building): MapPolygons {
  return building.polygons ?? [[building.coordinates]];
}

export function polygonShapes(polygons: MapPolygons): THREE.Shape[] {
  return polygons.map(([outer, ...holes]) => {
    const shape = new THREE.Shape(outer.map(([x, y]) => new THREE.Vector2(x, y)));
    shape.holes = holes.map(
      (ring) => new THREE.Path(ring.map(([x, y]) => new THREE.Vector2(x, y)))
    );
    return shape;
  });
}

export function polygonPath(polygons: MapPolygons): string {
  return polygons
    .map((polygon) =>
      polygon
        .map((ring) => ring.map(([x, y], i) => `${i ? 'L' : 'M'}${x},${-y}`).join(' ') + ' Z')
        .join(' ')
    )
    .join(' ');
}
