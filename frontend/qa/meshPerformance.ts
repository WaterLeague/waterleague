import {
  BufferAttribute,
  BufferGeometry,
  Mesh,
  MeshBasicMaterial,
  Raycaster,
  Vector3,
} from 'three';
import { CITY_HASH, loadCity } from '../src/domains/city/repository/cityRepository';
import { requestBuildingMesh } from '../src/domains/city/repository/buildingGeometryRepository';
import { buildingRaycast } from '../src/domains/city/service/buildingRaycastService';
import { loadTerrain } from '../src/domains/terrain/repository/terrainRepository';
import { terrainHeight } from '../src/domains/terrain/service/terrainService';
import { createTerrainGeometry } from '../src/domains/terrain/service/terrainMeshService';

export async function measurePublicMeshes() {
  const signal = new AbortController().signal;
  const [city, terrain] = await Promise.all([loadCity(signal), loadTerrain(signal)]);
  const buildings = city.overviewBuildings.map((b) => ({
    ...b,
    baseElevationM: terrainHeight(terrain, b.center),
  }));
  const start = performance.now();
  const data = await requestBuildingMesh(buildings, signal);
  const firstRequestMs = performance.now() - start;
  const cachedAt = performance.now();
  const reused = await requestBuildingMesh(structuredClone(buildings), signal);
  const cachedRequestMs = performance.now() - cachedAt;
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(data.positions, 3));
  geometry.setAttribute('normal', new BufferAttribute(data.normals, 3));
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  const mesh = new Mesh(geometry, new MeshBasicMaterial());
  const accelerated = buildingRaycast(data);
  const rays = buildings
    .filter((_, i) => i % Math.max(1, Math.floor(buildings.length / 96)) === 0)
    .slice(0, 96)
    .map(
      (b) =>
        new Raycaster(
          new Vector3(b.center[0], b.center[1], b.baseElevationM + b.heightM + 100),
          new Vector3(0, 0, -1)
        )
    );
  const originalMs: number[] = [],
    acceleratedMs: number[] = [];
  let sameIntersections = true;
  try {
    for (const ray of rays) {
      mesh.raycast = Mesh.prototype.raycast;
      const old = ray.intersectObject(mesh, false);
      mesh.raycast = accelerated;
      const next = ray.intersectObject(mesh, false);
      const values = (hits: typeof old) =>
        hits.map((h) => [h.faceIndex, h.distance, ...h.point.toArray()]);
      sameIntersections &&= JSON.stringify(values(old)) === JSON.stringify(values(next));
    }
    for (let pass = 0; pass < 7; pass++) {
      for (const [method, times] of (pass % 2
        ? [
            [accelerated, acceleratedMs],
            [Mesh.prototype.raycast, originalMs],
          ]
        : [
            [Mesh.prototype.raycast, originalMs],
            [accelerated, acceleratedMs],
          ]) as [Mesh['raycast'], number[]][]) {
        mesh.raycast = method;
        const at = performance.now();
        for (const ray of rays) ray.intersectObject(mesh, false);
        times.push(performance.now() - at);
      }
    }
    const source = { ...terrain };
    const terrainAt = performance.now();
    const first = createTerrainGeometry(source);
    const terrainFirstMs = performance.now() - terrainAt;
    const terrainAgainAt = performance.now();
    const second = createTerrainGeometry(source);
    const terrainReusedMs = performance.now() - terrainAgainAt;
    const sameTerrainBuffers =
      first.getAttribute('position').array === second.getAttribute('position').array &&
      first.getAttribute('normal').array === second.getAttribute('normal').array;
    first.dispose();
    second.dispose();
    const median = (values: number[]) =>
      [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];
    return {
      citySha256: CITY_HASH,
      buildingCount: buildings.length,
      triangleCount: data.positions.length / 9,
      rayCount: rays.length,
      sameIntersections,
      firstRequestMs,
      cachedRequestMs,
      sameCachedBuffers: data === reused,
      originalRaycastMedianMs: median(originalMs),
      acceleratedRaycastMedianMs: median(acceleratedMs),
      originalMs,
      acceleratedMs,
      terrainFirstMs,
      terrainReusedMs,
      sameTerrainBuffers,
      scope:
        '공개 서울 전체 보기 건물의 광선 판정·CPU 형상 재사용, 전체 사용자 선택 응답 시간 아님',
      userAgent: navigator.userAgent,
      viewport: [innerWidth, innerHeight],
    };
  } finally {
    geometry.dispose();
    mesh.material.dispose();
  }
}
