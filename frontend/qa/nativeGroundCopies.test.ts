import { readFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { expect, test } from 'vitest';
import { nativeBridgesDto } from '../src/domains/urban/dto/nativeBridgeDto';
import {
  connectBridgeDatums,
  nativeBridgeHeight,
  withinBridge,
} from '../src/domains/urban/service/nativeBridgeService';
import { bridgeTransportBindings } from '../src/domains/urban/service/nativeBridgeTransportService';
import { topographyGeometry } from '../src/domains/topography/service/topographyGeometryService';
import { topographyIndexDto, topographyTileDto } from '../src/domains/topography/dto/topographyDto';
const base = new URL('../public/data/', import.meta.url);
const body = nativeBridgesDto.parse(
  JSON.parse(
    gunzipSync(readFileSync(new URL('seoul-bridges-v1/structures.json.gz', base))).toString()
  )
);
const groups = connectBridgeDatums(body.groups, body.waterPolygons);
const bindings = bridgeTransportBindings(groups);
const index = topographyIndexDto.parse(
  JSON.parse(readFileSync(new URL('seoul-features-v1/index.json', base), 'utf8'))
);

test('양화대교 남단 실제 안전지대·도로 사본 제거와 외곽 9cm 바깥 원 난간 높이 귀속', () => {
  const entry = index.tiles.find((t) => t.id === '-8_-4')!;
  const tile = topographyTileDto.parse(
    JSON.parse(
      gunzipSync(readFileSync(new URL('seoul-features-v1/' + entry.file, base))).toString()
    )
  );
  const point: [number, number] = [-7031.918, -3324.027];
  const group = groups.find((g) => g.id.endsWith('a71967d6e201'))!;
  for (const fid of [1253704, 1253809]) {
    const row = tile.areas.find((a) => a[1] === fid)!;
    expect(withinBridge(point, row[2])).toBe(true);
    expect(
      withinBridge(point, bindings.groundCuts!.surface(row[2], index.layers[row[0]].role, fid))
    ).toBe(false);
  }
  const lower = tile.areas.find((a) => a[1] === 1253663)!;
  expect(
    withinBridge(
      point,
      bindings.groundCuts!.surface(lower[2], index.layers[lower[0]].role, lower[1])
    )
  ).toBe(true);
  const fence = tile.lines.find((a) => a[1] === 1255107)!;
  const part = fence[2].flat().filter((p) => p[1] > -3340 && p[1] < -3300);
  expect(part.length).toBeGreaterThan(2);
  expect(part.every((p) => !withinBridge(p, group.polygons))).toBe(true);
  const mesh = topographyGeometry(
    { ...tile, areas: [], points: [], lines: [[fence[0], fence[1], [part], null]] },
    index.layers,
    null,
    false,
    true,
    bindings
  );
  const heights = Array.from(mesh.positions).filter((_, i) => i % 3 === 1);
  expect(heights.length).toBeGreaterThan(0);
  expect(Math.min(...heights)).toBeGreaterThanOrEqual(
    nativeBridgeHeight(null, group.displayDatumPolygons!)
  );
});
for (const id of ['-2_-6', '1_-6', '7_-5', '-11_-1', '-11_0', '-10_0', '-8_-2', '-8_-3'])
  test(`실제 ${id} 교량 수면 구간의 도로·보도 지면 삼각형 중복 제거`, () => {
    const entry = index.tiles.find((t) => t.id === id)!;
    const raw = topographyTileDto.parse(
      JSON.parse(
        gunzipSync(readFileSync(new URL('seoul-features-v1/' + entry.file, base))).toString()
      )
    );
    const tile = {
      ...raw,
      points: [],
      lines: [],
      areas: raw.areas.filter((a) =>
        ['ROAD_AREA', 'SIDEWALK_AREA', 'RAILWAY_AREA'].includes(index.layers[a[0]].role)
      ),
    };
    const cuts = groups
      .filter(
        (g) =>
          g.bounds[0] <= entry.bounds[2] &&
          g.bounds[2] >= entry.bounds[0] &&
          g.bounds[1] <= entry.bounds[3] &&
          g.bounds[3] >= entry.bounds[1]
      )
      .flatMap((g) => g.groundCutPolygons ?? []);
    expect(cuts.length).toBeGreaterThan(0);
    const count = (positions: Float32Array) => {
      let inside = 0;
      for (let i = 0; i < positions.length; i += 9) {
        const a = [positions[i], -positions[i + 2]],
          b = [positions[i + 3], -positions[i + 5]],
          c = [positions[i + 6], -positions[i + 8]];
        const area = Math.abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2;
        if (area > 0.1 && withinBridge([(a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3], cuts))
          inside++;
      }
      return inside;
    };
    expect(
      count(topographyGeometry(tile, index.layers, null, false, true).positions)
    ).toBeGreaterThan(0);
    expect(
      count(topographyGeometry(tile, index.layers, null, false, true, bindings).positions)
    ).toBe(0);
    const boundary = {
      ...tile,
      areas: [],
      lines: raw.lines.filter((a) => index.layers[a[0]].id === 'N1L_A0010000'),
    };
    const lines = topographyGeometry(boundary, index.layers, null, false, true, bindings).lines;
    for (let i = 0; i < lines.length; i += 6) {
      const a = [lines[i], -lines[i + 2]],
        b = [lines[i + 3], -lines[i + 5]];
      if (Math.hypot(a[0] - b[0], a[1] - b[1]) > 0.01)
        expect(
          [
            [0.002, 0],
            [-0.002, 0],
            [0, 0.002],
            [0, -0.002],
          ].every(([dx, dy]) =>
            withinBridge([(a[0] + b[0]) / 2 + dx, (a[1] + b[1]) / 2 + dy], cuts)
          ),
          JSON.stringify({ a, b })
        ).toBe(false);
    }
  }, 30000);

for (const id of ['-2_-6', '1_-6', '7_-5', '-11_-1', '-11_0', '-8_-2'])
  test(`실제 ${id} 수면 위 교량 조명이 지면에 남지 않고 원래 개수 유지`, () => {
    const entry = index.tiles.find((t) => t.id === id)!;
    const raw = topographyTileDto.parse(
      JSON.parse(
        gunzipSync(readFileSync(new URL('seoul-features-v1/' + entry.file, base))).toString()
      )
    );
    const points = raw.points
      .filter((row) => index.layers[row[0]].id.slice(4, 8) === 'C022')
      .map(
        (row) =>
          [
            row[0],
            row[1],
            row[2].filter((p) =>
              bindings.groundCuts!.at(p).some((g) => withinBridge(p, g.polygons))
            ),
            row[3],
          ] as typeof row
      )
      .filter((row) => row[2].length);
    const expected = points.reduce((n, p) => n + p[2].length, 0);
    expect(expected).toBeGreaterThan(0);
    const mesh = topographyGeometry(
      { ...raw, points, lines: [], areas: [] },
      index.layers,
      null,
      false,
      true,
      bindings
    );
    const matrices = mesh.models.flatMap((m) => Array.from(m.matrices));
    expect(matrices.length / 16).toBe(expected);
    for (let i = 13; i < matrices.length; i += 16) expect(matrices[i]).toBeGreaterThan(6);
  });

for (const id of ['-2_-6', '-11_-1', '-10_0', '-7_-3', '-7_-4', '-5_-4'])
  test(`실제 ${id} 육지·섬 통과부에서 교량 원 면과 같은 통행면의 지면 사본 제거`, () => {
    const entry = index.tiles.find((t) => t.id === id)!;
    const raw = topographyTileDto.parse(
      JSON.parse(
        gunzipSync(readFileSync(new URL('seoul-features-v1/' + entry.file, base))).toString()
      )
    );
    let before = 0;
    for (const role of ['ROAD_AREA', 'SIDEWALK_AREA', 'RAILWAY_AREA']) {
      const cuts = groups
        .filter(
          (g) =>
            g.bounds[0] <= entry.bounds[2] + 125 &&
            g.bounds[2] >= entry.bounds[0] - 125 &&
            g.bounds[1] <= entry.bounds[3] + 125 &&
            g.bounds[3] >= entry.bounds[1] - 125
        )
        .flatMap((g) =>
          (g.surfaceCuts ?? [])
            .filter((cut) => cut.roles.includes(role as 'ROAD_AREA'))
            .flatMap((cut) => cut.polygons)
        );
      const tile = {
        ...raw,
        points: [],
        lines: [],
        areas: raw.areas.filter(([layer]) => index.layers[layer].role === role),
      };
      const count = (positions: Float32Array) => {
        let n = 0;
        for (let i = 0; i < positions.length; i += 9) {
          const a = [positions[i], -positions[i + 2]],
            b = [positions[i + 3], -positions[i + 5]],
            c = [positions[i + 6], -positions[i + 8]];
          if (Math.abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) < 0.2)
            continue;
          const x = (a[0] + b[0] + c[0]) / 3,
            y = (a[1] + b[1] + c[1]) / 3;
          if (
            [
              [0.002, 0],
              [-0.002, 0],
              [0, 0.002],
              [0, -0.002],
            ].every(([dx, dy]) => withinBridge([x + dx, y + dy], cuts))
          )
            n++;
        }
        return n;
      };
      before += count(topographyGeometry(tile, index.layers, null, false, true).positions);
      expect(
        count(topographyGeometry(tile, index.layers, null, false, true, bindings).positions),
        role
      ).toBe(0);
    }
    expect(before).toBeGreaterThan(0);
    const bridges = {
      ...raw,
      points: [],
      lines: [],
      areas: raw.areas.filter(([layer]) =>
        ['BRIDGE_AREA', 'PEDESTRIAN_OVERPASS_AREA', 'GRADE_SEPARATED_INTERSECTION_AREA'].includes(
          index.layers[layer].role
        )
      ),
    };
    const mesh = topographyGeometry(bridges, index.layers, null, false, true, bindings);
    expect(mesh.positions.length + mesh.lines.length).toBe(0);
  }, 30000);
