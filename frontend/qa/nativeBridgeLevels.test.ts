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
  Vector2,
  ShapeUtils,
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
const body = nativeBridgesDto.parse(
  JSON.parse(
    gunzipSync(readFileSync(new URL('seoul-bridges-v1/structures.json.gz', base))).toString()
  )
);
const groups = connectBridgeDatums(body.groups, body.waterPolygons);
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

test('원 레코드로 결속된 중심선만 상판으로 올리고 반포 아래 도로는 상층과 분리', () => {
  const bindings = bridgeTransportBindings(groups);
  expect(bindings.size).toBeGreaterThan(1000);
  const group = groups.find((g) => g.lowerDeck?.name === '잠수교')!;
  const profile = group.profiles[0];
  const height = bridgeTransportHeight(bindings.get(profile.sourceFids![0]), terrain)!;
  const p = profile.coordinates.at(-1)!;
  expect(height(p)).toBeCloseTo(nativeBridgeHeight(terrain, group.displayDatumPolygons!, 13.5));
  expect(bridgeTransportBindings([group]).has(1839612)).toBe(false);
  const underpass: [number, number] = [1735.0020790235994, -6343.088847466795];
  expect(bridgeTransportHeight(bindings.get(1839612), terrain)!(underpass)).toBeLessThan(
    nativeBridgeHeight(terrain, group.displayDatumPolygons!, 13.5) - 1
  );
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
}, 30000);

test('노들섬 양쪽 한강대교는 노량대교와 분리되고 같은 상판 높이 기준 사용', () => {
  for (const [north, south] of [
    [1823862, 1823865],
    [1823863, 1823864],
  ]) {
    const group = groups.find((g) => g.sourceFids.includes(north))!;
    expect(group.sourceFids).toContain(south);
    expect(group.names).not.toContain('노량대교');
    expect(group.sourceFids).not.toContain(1835242);
    const streets = nativeStreets([], [group]);
    const bridge = streets.find((s) => s.id === group.id)!;
    const points = group.polygons.map((p) => p[0][0]);
    expect(new Set(points.map((p) => streetHeight(terrain, p, bridge))).size).toBe(1);
  }
});

test('모든 교량의 표시 접속로는 수면 안으로 연장된 중복 면과 철길을 생성하지 않음', () => {
  let tested = 0;
  const all = nativeStreets([], groups);
  for (const group of groups.filter((g) => g.groundCutPolygons?.length)) {
    for (const road of all.filter(
      (s) => s.id.startsWith(group.id + ':') && s.nativeBridgeProfiles?.length && !s.bridge
    )) {
      expect(road.nativeRailPaths).toBeUndefined();
      for (const polygon of road.nativePolygons ?? []) {
        const rings = polygon.map((r) => r.slice(0, -1).map((p) => new Vector2(...p))),
          vertices = rings.flat();
        for (const ids of ShapeUtils.triangulateShape(rings[0], rings.slice(1))) {
          const [a, b, c] = ids.map((i) => vertices[i]);
          if (Math.abs((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)) < 0.2) continue;
          expect(
            withinBridge([(a.x + b.x + c.x) / 3, (a.y + b.y + c.y) / 3], group.groundCutPolygons!),
            JSON.stringify({ id: road.id, a, b, c })
          ).toBe(false);
          tested++;
        }
      }
    }
  }
  expect(tested).toBeGreaterThan(1000);
}, 30000);
