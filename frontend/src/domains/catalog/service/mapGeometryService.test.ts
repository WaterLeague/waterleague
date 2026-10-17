import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import snapshot from '../../../../public/data/seongsu-ngii-v2.json';
import { mapDto } from '../dto/catalogDto';
import { toCandidateMap } from '../mapper/catalogMapper';
import {
  buildingPolygons,
  polygonShapes,
  polygonPath,
  type MapPolygons,
} from './mapGeometryService';

describe('수치지도 원형 렌더링', () => {
  it('공개 건물 246개와 교통 면의 형상을 유지', () => {
    const map = toCandidateMap(mapDto.parse(snapshot));
    expect(map.buildings).toHaveLength(246);
    expect(map.roads).toHaveLength(0);
    expect(map.transports).toHaveLength(87);
    expect(map.buildings.every((b) => buildingPolygons(b).length > 0)).toBe(true);
  });
  it('구멍과 복수 면을 3D 삼각형과 2D 경로에서 보존', () => {
    const polygons: MapPolygons = [
      [
        [
          [0, 0],
          [10, 0],
          [10, 10],
          [0, 10],
          [0, 0],
        ],
        [
          [2, 2],
          [8, 2],
          [8, 8],
          [2, 8],
          [2, 2],
        ],
      ],
      [
        [
          [20, 0],
          [22, 0],
          [22, 2],
          [20, 2],
          [20, 0],
        ],
      ],
    ];
    const shapes = polygonShapes(polygons);
    expect(shapes).toHaveLength(2);
    const geometry = new THREE.ShapeGeometry(shapes);
    const vertices = geometry.getAttribute('position');
    const index = geometry.index!;
    let area = 0;
    for (let i = 0; i < index.count; i += 3) {
      const a = new THREE.Vector3().fromBufferAttribute(vertices, index.getX(i));
      const b = new THREE.Vector3().fromBufferAttribute(vertices, index.getX(i + 1));
      const c = new THREE.Vector3().fromBufferAttribute(vertices, index.getX(i + 2));
      area += b.sub(a).cross(c.sub(a)).length() / 2;
    }
    expect(area).toBeCloseTo(68, 8);
    expect(polygonPath(polygons).match(/ Z/g)).toHaveLength(3);
    geometry.dispose();
  });
});
