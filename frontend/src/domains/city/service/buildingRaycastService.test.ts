import { expect, test, vi } from 'vitest';
import {
  BufferAttribute,
  BufferGeometry,
  DoubleSide,
  Mesh,
  MeshBasicMaterial,
  Raycaster,
  Vector3,
} from 'three';
import { buildBuildingMesh } from './buildingGeometryService';
import { buildingRaycast } from './buildingRaycastService';
import { buildingFaceIndex } from './buildingSelectionService';
import type { CityBuilding } from '../entity/city';

const buildings: CityBuilding[] = [
  {
    id: 'way/1',
    center: [15, 15],
    areaM2: 800,
    heightM: 20,
    baseElevationM: 100,
    heightSource: 'OSM_HEIGHT_TAG',
    polygons: [
      [
        [
          [0, 0],
          [30, 0],
          [30, 30],
          [0, 30],
          [0, 0],
        ],
        [
          [10, 10],
          [10, 20],
          [20, 20],
          [20, 10],
          [10, 10],
        ],
      ],
    ],
  },
  {
    id: 'way/2',
    center: [60, 15],
    areaM2: 900,
    heightM: 40,
    baseElevationM: 130,
    heightSource: 'OSM_HEIGHT_TAG',
    polygons: [
      [
        [
          [45, 0],
          [75, 0],
          [75, 30],
          [45, 30],
          [45, 0],
        ],
      ],
    ],
  },
];
function fixture() {
  const data = buildBuildingMesh(buildings);
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(data.positions, 3));
  geometry.setAttribute('normal', new BufferAttribute(data.normals, 3));
  const mesh = new Mesh(geometry, new MeshBasicMaterial({ side: DoubleSide }));
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.set(3, 7, 11);
  mesh.scale.set(1.2, 0.8, 1.5);
  mesh.updateMatrixWorld();
  return { data, mesh };
}
test('원본 광선 판정의 높이·중정·면 번호·다중 건물·거리 제한 보존', () => {
  const { data, mesh } = fixture();
  const raycast = buildingRaycast(data);
  for (const [from, to] of [
    [
      [5, 5, 250],
      [5, 5, 0],
    ],
    [
      [15, 15, 250],
      [15, 15, 0],
    ],
    [
      [60, 15, 250],
      [60, 15, 0],
    ],
    [
      [-20, 5, 110],
      [100, 5, 110],
    ],
    [
      [-20, 5, 135],
      [100, 5, 135],
    ],
    [
      [32, 50, 250],
      [32, 50, 0],
    ],
  ]) {
    const origin = new Vector3(...from).applyMatrix4(mesh.matrixWorld);
    const direction = new Vector3(...to).applyMatrix4(mesh.matrixWorld).sub(origin).normalize();
    for (const far of [10, Infinity]) {
      const ray = new Raycaster(origin, direction, 0, far);
      mesh.raycast = Mesh.prototype.raycast;
      const before = ray.intersectObject(mesh, false);
      mesh.raycast = raycast;
      const after = ray.intersectObject(mesh, false);
      const result = (hits: typeof before) =>
        hits.map((h) => ({
          face: h.faceIndex,
          point: h.point.toArray(),
          distance: h.distance,
          building: buildingFaceIndex(data.ends, h.faceIndex!),
        }));
      expect(result(after)).toEqual(result(before));
      expect(mesh.geometry.drawRange).toEqual({ start: 0, count: Infinity });
    }
  }
  mesh.geometry.setDrawRange(data.ends[0] * 3, (data.ends[1] - data.ends[0]) * 3);
  const range = { ...mesh.geometry.drawRange };
  mesh.raycast(new Raycaster(new Vector3(0, 500, 0), new Vector3(0, -1, 0)), []);
  expect(mesh.geometry.drawRange).toEqual(range);
  mesh.geometry.dispose();
  mesh.material.dispose();
});

test('넓은 빈 공간은 면 검사 생략·검사 예외에도 표시 범위 복원', () => {
  const { data, mesh } = fixture();
  mesh.raycast = buildingRaycast(data);
  const probe = vi.spyOn(Mesh.prototype, 'raycast');
  const ray = (x: number, y: number) => {
    const origin = new Vector3(x, y, 250).applyMatrix4(mesh.matrixWorld);
    return new Raycaster(
      origin,
      new Vector3(x, y, 0).applyMatrix4(mesh.matrixWorld).sub(origin).normalize()
    );
  };
  try {
    mesh.raycast(ray(35, 15), []);
    expect(probe).not.toHaveBeenCalled();
    mesh.raycast(ray(5, 5), []);
    expect(probe).toHaveBeenCalledTimes(1);
    probe.mockImplementation(() => {
      throw new Error('검사 실패');
    });
    expect(() => mesh.raycast(ray(60, 15), [])).toThrow('검사 실패');
    expect(mesh.geometry.drawRange).toEqual({ start: 0, count: Infinity });
  } finally {
    probe.mockRestore();
    mesh.geometry.dispose();
    mesh.material.dispose();
  }
});
