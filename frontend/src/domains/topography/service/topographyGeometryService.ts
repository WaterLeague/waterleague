import bridgeIndex from '../../../../public/data/seoul-bridges-v1/index.json';
import { stairTriangles } from '../../../shared/service/polygonBandService';
import { BufferGeometry, Color, Float32BufferAttribute, ShapeUtils, Vector2 } from 'three';
import type { TopographyIndex, TopographyTile } from '../dto/topographyDto';
import type { TopographyBuffers } from '../entity/topography';
import type { Terrain } from '../../terrain/entity/terrain';
import { modelMatrix, pointModelKind, type PointModelKind } from './pointModelService';
import { topographyStyle } from './topographyStyleService';
import { areaLift, structureWriter } from './structureGeometryService';
import { nativeBridgeHeight } from '../../urban/service/nativeBridgeService';
import {
  bridgeTransportHeight,
  type NativeBridgeTransport,
} from '../../urban/service/nativeBridgeTransportService';
import {
  drapeTriangle,
  drapeSegment,
  terrainMeshHeight,
} from '../../terrain/service/terrainDrapeService';
const bridgeStairFids = new Set(bridgeIndex.stairFids);
type Point = [number, number];
export function topographyGeometry(
  tile: TopographyTile,
  layers: TopographyIndex['layers'],
  terrain: Terrain | null,
  plan: boolean,
  structuresLoaded = false,
  transport?: NativeBridgeTransport
): TopographyBuffers {
  const positions: number[] = [],
    colors: number[] = [],
    lines: number[] = [],
    lineColors: number[] = [];
  const models = new Map<
    string,
    { kind: PointModelKind; cell: [number, number]; values: number[] }
  >();
  const structures = structureWriter(positions, colors, terrain);
  const labels: TopographyBuffers['labels'] = [],
    plans = new Map<number, { areas: string[]; lines: string[]; points: string[] }>();
  const styles = layers.map(topographyStyle),
    style = styles.map((value) => new Color(value.color));
  const path = (ring: Point[], close = false) =>
    ring.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(3)},${(-y).toFixed(3)}`).join('') +
    (close ? 'Z' : '');
  const group = (layer: number) => {
    let value = plans.get(layer);
    if (!value) {
      value = { areas: [], lines: [], points: [] };
      plans.set(layer, value);
    }
    return value;
  };
  for (const [layer, , parts, label] of tile.points) {
    for (const point of parts) {
      const [x, y] = point;
      if (!plan) {
        const model = pointModelKind(layers[layer].id) ?? (!label ? 'SURVEY' : null);
        if (model) {
          const cell: [number, number] = [Math.floor(x / 100), Math.floor(y / 100)],
            key = model + ':' + cell.join(',');
          if (!models.has(key)) models.set(key, { kind: model, cell, values: [] });
          models
            .get(key)!
            .values.push(...modelMatrix(x, terrainMeshHeight(terrain, point) + 0.08, -y, 0));
        }
      }
      if (plan)
        group(layer).points.push(
          `M${(x - 0.7).toFixed(3)},${(-y).toFixed(3)}a.7,.7 0 1 0 1.4,0a.7,.7 0 1 0 -1.4,0`
        );
      if (label) labels.push({ point, text: label, layer });
    }
  }
  for (const [layer, fid, parts] of tile.lines) {
    const color = style[layer];
    const height = plan ? undefined : bridgeTransportHeight(transport?.get(fid), terrain);
    const writer = height ? structureWriter(positions, colors, terrain, height) : structures;
    for (const part of parts) {
      if (plan) group(layer).lines.push(path(part));
      if (plan) continue;
      if (writer.line(layers[layer].id, part, color)) continue;
      for (let i = 1; i < part.length; i++)
        for (const segment of drapeSegment(part[i - 1], part[i], terrain))
          for (const point of segment) {
            lines.push(point[0], terrainMeshHeight(terrain, point) + 0.09, -point[1]);
            lineColors.push(color.r, color.g, color.b);
          }
    }
  }
  for (const [layer, fid, polygons] of tile.areas) {
    if (structuresLoaded && !plan && bridgeStairFids.has(fid)) continue;
    const color = style[layer];
    for (const polygon of polygons) {
      if (plan)
        group(layer)[styles[layer].fill ? 'areas' : 'lines'].push(
          polygon.map((ring) => path(ring, true)).join('')
        );
      if (plan) continue;
      if (
        structuresLoaded &&
        ['PEDESTRIAN_OVERPASS_AREA', 'GRADE_SEPARATED_INTERSECTION_AREA'].includes(
          layers[layer].role
        )
      )
        continue;
      const rings = polygon.map((ring) => ring.slice(0, -1).map(([x, y]) => new Vector2(x, y))),
        vertices = rings.flat();
      const lift = areaLift(layers[layer].id);
      const stairs = layers[layer].id.slice(4, 8) === 'C039';
      const canopy = layers[layer].id.slice(4, 8) === 'A020';
      let axis: Point = [1, 0],
        longest = 0;
      for (const ring of polygon)
        for (let i = 1; i < ring.length; i++) {
          const dx = ring[i][0] - ring[i - 1][0],
            dy = ring[i][1] - ring[i - 1][1],
            length = Math.hypot(dx, dy);
          if (length > longest) {
            longest = length;
            axis = [dx / length, dy / length];
          }
        }
      const projections = polygon[0].map((p) => p[0] * axis[0] + p[1] * axis[1]),
        start = Math.min(...projections),
        span = Math.max(...projections) - start,
        step = Math.max(0.35, span / 256),
        rise = Math.min(0.16, 3 / (Math.ceil(span / step) || 1));
      const deck =
        layers[layer].role === 'PEDESTRIAN_OVERPASS_AREA'
          ? nativeBridgeHeight(terrain, [polygon])
          : null;
      for (const ids of styles[layer].fill
        ? ShapeUtils.triangulateShape(rings[0], rings.slice(1))
        : []) {
        const triangle = ids.map((id) => [vertices[id].x, vertices[id].y] as Point) as [
          Point,
          Point,
          Point,
        ];
        const emit = (part: readonly (readonly [number, number])[]) => {
          for (const point of part) {
            positions.push(point[0], (deck ?? terrainMeshHeight(terrain, point)) + lift, -point[1]);
            colors.push(color.r, color.g, color.b);
          }
        };
        if (stairs)
          for (const section of stairTriangles(triangle, axis, start, step)) {
            const h = 0.055 + (section.band + 1) * rise;
            for (let i = 1; i < section.points.length - 1; i++)
              structures.triangle(
                structures.vertex(section.points[0], h),
                structures.vertex(section.points[i], h),
                structures.vertex(section.points[i + 1], h),
                color
              );
            structures.sides([[...section.points, section.points[0]]], h, color);
          }
        else if (deck === null) drapeTriangle(triangle, terrain, emit);
        else emit(triangle);
      }
      if (!stairs && lift > 0.055) structures.sides(polygon, lift, color, canopy ? lift - 0.25 : 0);
      if (canopy) {
        let walked = 0,
          next = 0;
        for (let i = 1; i < polygon[0].length; i++) {
          const a = polygon[0][i - 1],
            b = polygon[0][i];
          const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
          for (; next < walked + length; next += 12) {
            const t = (next - walked) / length;
            const p: Point = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
            structures.beam(p, [p[0] + 0.1, p[1]], 0.65, lift - 0.9, 0.2, color);
          }
          walked += length;
        }
      }
      for (const ring of polygon)
        for (let i = 1; i < ring.length; i++)
          for (const segment of drapeSegment(ring[i - 1], ring[i], terrain))
            for (const point of segment) {
              lines.push(
                point[0],
                (deck ?? terrainMeshHeight(terrain, point)) + lift + 0.003,
                -point[1]
              );
              lineColors.push(color.r * 0.8, color.g * 0.8, color.b * 0.8);
            }
    }
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(positions, 3));
  geometry.computeVertexNormals();
  const normals = geometry.getAttribute('normal').array as Float32Array;
  geometry.dispose();
  if (positions.length + lines.length > 18000000) throw new Error('지형지물 형상 상한 초과');
  return {
    models: [...models.values()].map(({ kind, cell, values }) => ({
      kind,
      cell,
      matrices: new Float32Array(values),
    })),
    positions: new Float32Array(positions),
    colors: new Float32Array(colors),
    normals,
    lines: new Float32Array(lines),
    lineColors: new Float32Array(lineColors),
    plan: [...plans].map(([layer, value]) => ({
      layer,
      areas: value.areas.join(''),
      lines: value.lines.join(''),
      points: value.points.join(''),
    })),
    labels,
    counts: { points: tile.points.length, lines: tile.lines.length, areas: tile.areas.length },
  };
}
