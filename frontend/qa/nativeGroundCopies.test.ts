import { readFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { expect, test } from 'vitest';
import { nativeBridgesDto } from '../src/domains/urban/dto/nativeBridgeDto';
import {
  connectBridgeDatums,
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
