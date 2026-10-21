import { readFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { expect, test } from 'vitest';
import {
  BufferAttribute,
  BufferGeometry,
  DoubleSide,
  Mesh,
  MeshBasicMaterial,
  Raycaster,
  Vector3,
} from 'three';
import { nativeBridgesDto } from '../src/domains/urban/dto/nativeBridgeDto';
import {
  connectBridgeDatums,
  nativeBridgeHeight,
  withinBridge,
} from '../src/domains/urban/service/nativeBridgeService';
import {
  bridgeTransportBindings,
  bridgeTransportHeight,
} from '../src/domains/urban/service/nativeBridgeTransportService';
import { nativeStreets } from '../src/domains/urban/service/nativeStreetService';
import { streetGeometry, streetHeight } from '../src/domains/urban/service/streetGeometryService';
import { terrainMeshHeight } from '../src/domains/terrain/service/terrainDrapeService';
import type { Terrain } from '../src/domains/terrain/entity/terrain';
const base = new URL('../public/data/', import.meta.url);
const groups = connectBridgeDatums(
  nativeBridgesDto.parse(
    JSON.parse(
      gunzipSync(readFileSync(new URL('seoul-bridges-v1/structures.json.gz', base))).toString()
    )
  ).groups
);
const info = JSON.parse(
  readFileSync(new URL('seoul-terrain-native-v1/terrain.json', base), 'utf8')
);
const heights = readFileSync(new URL('seoul-terrain-native-v1/height-f32le.bin', base));
const terrain: Terrain = {
  ...info,
  heights: new Float32Array(
    heights.buffer.slice(heights.byteOffset, heights.byteOffset + heights.byteLength)
  ),
  districts: new Uint8Array(),
  cover: new Uint8Array(),
};

test('실제 반포·청담 원본에서 하층 상판·보행로·선로가 수면 위에 있고 상층과 7m 분리', () => {
  const selected = groups.filter((g) => g.lowerDeck);
  expect(selected.map((g) => g.lowerDeck!.name).sort()).toEqual(['잠수교', '청담대교 하부 전철']);
  for (const group of selected) {
    const streets = nativeStreets([], [group]);
    const lower = streets.find((s) => s.id === group.id + ':lower')!;
    const upper = streets.find((s) => s.id === group.id)!;
    const deck = nativeBridgeHeight(terrain, group.displayDatumPolygons ?? group.polygons);
    const paths = [...group.lowerDeck!.walkPaths, ...group.lowerDeck!.railPaths];
    expect(paths.length).toBeGreaterThan(0);
    let samples = 0;
    for (const path of paths)
      for (let i = 1; i < path.length; i++) {
        const a = path[i - 1],
          b = path[i];
        const count = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 10));
        for (let j = 0; j <= count; j++) {
          const p: [number, number] = [
            a[0] + ((b[0] - a[0]) * j) / count,
            a[1] + ((b[1] - a[1]) * j) / count,
          ];
          expect(withinBridge(p, group.lowerDeck!.polygons)).toBe(true);
          expect(streetHeight(terrain, p, lower)).toBeCloseTo(deck + 0.016);
          expect(streetHeight(terrain, p, upper) - streetHeight(terrain, p, lower)).toBeCloseTo(7);
          expect(
            streetHeight(terrain, p, lower) - terrainMeshHeight(terrain, p) - 0.25
          ).toBeGreaterThan(1);
          samples++;
        }
      }
    expect(samples).toBeGreaterThan(150);
    for (const walk of streets.filter((s) => s.walk && s.nativeDeckLevel === 'lower'))
      for (const p of walk.coordinates)
        expect(streetHeight(terrain, p, walk)).toBeCloseTo(deck + 0.14);
    const mesh = streetGeometry(
      streets.filter((s) => s.nativeDeckLevel === 'lower'),
      terrain,
      true
    );
    expect(mesh.positions.every(Number.isFinite)).toBe(true);
    const geometry = new BufferGeometry().setAttribute(
      'position',
      new BufferAttribute(mesh.positions, 3)
    );
    const material = new MeshBasicMaterial({ side: DoubleSide });
    const p = paths[0][Math.floor(paths[0].length / 2)];
    const hits = new Raycaster(
      new Vector3(p[0], deck + 5, -p[1]),
      new Vector3(0, -1, 0)
    ).intersectObject(new Mesh(geometry, material));
    expect(hits.length).toBeGreaterThan(0);
    expect(hits[0].point.y).toBeGreaterThanOrEqual(deck);
    expect(hits[0].point.y).toBeLessThan(deck + 1.2);
    geometry.dispose();
    material.dispose();
  }
});

test('청담대교 원본 교량·고가 분류 경계의 상판 높이 기준 공유', () => {
  const named = groups.filter((g) => g.names?.includes('청담대교'));
  expect(named.length).toBeGreaterThan(1);
  expect(new Set(named.map((g) => g.displayDatumPolygons)).size).toBe(1);
  expect(
    new Set(named.map((g) => nativeBridgeHeight(terrain, g.displayDatumPolygons!, 13.5))).size
  ).toBe(1);
});

test('원 레코드로 결속된 중심선만 상판으로 올리고 반포 아래 올림픽대로는 지상 유지', () => {
  const bindings = bridgeTransportBindings(groups);
  expect(bindings.size).toBeGreaterThan(1000);
  const group = groups.find((g) => g.lowerDeck?.name === '잠수교')!;
  const profile = group.profiles[0];
  const height = bridgeTransportHeight(bindings.get(profile.sourceFids![0]), terrain)!;
  const p = profile.coordinates.at(-1)!;
  expect(height(p)).toBeCloseTo(nativeBridgeHeight(terrain, group.displayDatumPolygons!, 13.5));
  expect(bindings.has(1839612)).toBe(false);
  expect(bridgeTransportHeight(bindings.get(1839612), terrain)).toBeUndefined();
});

test('교량 접속부가 하층을 가리는 지면까지의 수직 벽을 만들지 않음', () => {
  const group = groups.find((g) => g.lowerDeck?.name === '잠수교')!;
  for (const road of nativeStreets([], [group]).filter((s) => s.nativeBridgeProfiles?.length)) {
    const mesh = streetGeometry([road], terrain, true);
    for (let i = 0; i < mesh.positions.length; i += 3) {
      const p: [number, number] = [mesh.positions[i], -mesh.positions[i + 2]];
      const height = streetHeight(terrain, p, road);
      const ground = terrainMeshHeight(terrain, p);
      if (height > ground + 2) expect(mesh.positions[i + 1]).toBeGreaterThan(ground + 1);
    }
  }
});
