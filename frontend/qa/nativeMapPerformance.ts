import { ExtrudeGeometry } from 'three';
import { CITY_HASH, loadCity, loadCityTile } from '../src/domains/city/repository/cityRepository';
import { buildBuildingMesh } from '../src/domains/city/service/buildingGeometryService';
import { polygonShapes } from '../src/domains/catalog/service/mapGeometryService';
export async function measureNativeMapBuild() {
  const signal = new AbortController().signal;
  const city = await loadCity(signal);
  const entries = [...city.tiles].sort((a, b) => b.buildingCount - a.buildingCount).slice(0, 2);
  const tiles = await Promise.all(entries.map((entry) => loadCityTile(entry, signal)));
  const buildings = tiles.flatMap((tile) => tile.buildings).slice(0, 6000);
  const original: number[] = [],
    direct: number[] = [];
  let originalVertices = 0,
    directVertices = 0;
  for (let pass = 0; pass < 5; pass++) {
    const old = () => {
      const at = performance.now();
      const parts = buildings.map(
        (building) =>
          new ExtrudeGeometry(polygonShapes(building.polygons), {
            depth: building.heightM,
            bevelEnabled: false,
            steps: 1,
          })
      );
      originalVertices = parts.reduce((n, part) => n + part.getAttribute('position').count, 0);
      const positions = new Float32Array(originalVertices * 3),
        normals = new Float32Array(originalVertices * 3);
      let offset = 0;
      for (const part of parts) {
        positions.set(part.getAttribute('position').array, offset);
        normals.set(part.getAttribute('normal').array, offset);
        offset += part.getAttribute('position').array.length;
        part.dispose();
      }
      original.push(performance.now() - at);
    };
    const next = () => {
      const at = performance.now(),
        data = buildBuildingMesh(buildings);
      directVertices = data.positions.length / 3;
      direct.push(performance.now() - at);
    };
    if (pass % 2) {
      next();
      old();
    } else {
      old();
      next();
    }
  }
  const median = (values: number[]) =>
    [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];
  return {
    sourceCitySha256: CITY_HASH,
    sourceTiles: entries.map((entry) => entry.sha256),
    buildingCount: buildings.length,
    originalMs: original,
    directMs: direct,
    originalMedianMs: median(original),
    directMedianMs: median(direct),
    cpuSpeedup: median(original) / median(direct),
    originalVertices,
    directVertices,
    userAgent: navigator.userAgent,
    viewport: [innerWidth, innerHeight],
    scope: '같은 원형 건물 6천 개의 CPU 형상 생성 비교, 전체 로딩·FPS와 구분',
  };
}
