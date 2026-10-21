import { NativeGroundCuts } from '../../urban/service/nativeGroundCutService';
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
  bridgeAttachmentHeight,
  bridgeAttachmentSupports,
  bridgeSurfaceSupports,
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
  const roadAreas = tile.areas
    .filter(([layer]) => layers[layer].role === 'ROAD_AREA')
    .flatMap(([, , p]) => p);
  const sidewalkAreas = tile.areas
    .filter(([layer]) => layers[layer].role === 'SIDEWALK_AREA')
    .flatMap(([, , p]) => p);
  const roadCoverage = new NativeGroundCuts([], roadAreas);
  const sidewalkCoverage = new NativeGroundCuts([], sidewalkAreas);
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
          const attachment = [
            'BUS_STOP',
            'LAMP',
            'UTILITY_POLE',
            'SIGNAL',
            'SIGN',
            'BARRIER',
            'MIRROR',
            'TOLL',
          ].includes(model);
          const water = attachment
            ? (transport?.attachmentCuts ?? transport?.groundCuts)?.at(point)
            : undefined;
          const onWater = transport?.groundCuts?.contains(point) ?? false;
          const decks = water ? bridgeAttachmentSupports(water, point) : undefined;
          if (attachment && onWater && !decks?.length) continue;
          const elevation = decks?.length
            ? bridgeAttachmentHeight(decks, terrain)(point)
            : terrainMeshHeight(terrain, point);
          const cell: [number, number] = [Math.floor(x / 100), Math.floor(y / 100)],
            key = model + ':' + cell.join(',');
          if (!models.has(key)) models.set(key, { kind: model, cell, values: [] });
          models.get(key)!.values.push(...modelMatrix(x, elevation + 0.08, -y, 0));
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
    const rail = ['A015', 'A017'].includes(layers[layer].id.slice(4, 8));
    const attachment = ['C052', 'C053', 'B002'].includes(layers[layer].id.slice(4, 8));
    if (!plan && attachment && transport?.attachmentCuts) {
      const cuts = transport.attachmentCuts;
      for (const part of parts) {
        for (const ground of cuts
          .line(part)
          .flatMap((p) => transport.groundCuts?.line(p, false, 'ATTACHMENT_OUTSIDE') ?? [p]))
          structures.line(layers[layer].id, ground, color);
        for (const segment of cuts.line(part, true)) {
          const a = segment[0],
            b = segment.at(-1)!;
          const middle: Point = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
          const groups = bridgeAttachmentSupports(cuts.at(middle), middle, [a, b]);
          if (!groups.length && transport.groundCuts?.contains(middle)) continue;
          const height = groups.length ? bridgeAttachmentHeight(groups, terrain) : undefined;
          structureWriter(positions, colors, terrain, height).line(
            layers[layer].id,
            segment,
            color
          );
        }
      }
      continue;
    }
    if (!plan && (attachment || rail) && transport?.groundCuts) {
      const sourceHeight = rail ? bridgeTransportHeight(transport.get(fid), terrain) : undefined;
      const groundWriter = sourceHeight
        ? structureWriter(positions, colors, terrain, sourceHeight)
        : structures;
      for (const part of parts) {
        for (const ground of transport.groundCuts.line(
          part,
          false,
          rail ? 'RAILWAY_AREA' : undefined
        ))
          groundWriter.line(layers[layer].id, ground, color);
        for (const deck of transport.groundCuts.line(
          part,
          true,
          rail ? 'RAILWAY_AREA' : undefined
        )) {
          const a = deck[0],
            b = deck.at(-1)!;
          const middle: Point = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
          const groups = bridgeSurfaceSupports(
            transport.groundCuts.at(middle),
            middle,
            transport.groundCuts.contains(middle)
          );
          if (!groups.length || (rail && !sourceHeight)) continue;
          structureWriter(
            positions,
            colors,
            terrain,
            rail ? sourceHeight : bridgeAttachmentHeight(groups, terrain)
          ).line(layers[layer].id, deck, color);
        }
      }
      continue;
    }
    const height = plan ? undefined : bridgeTransportHeight(transport?.get(fid), terrain);
    const writer = height ? structureWriter(positions, colors, terrain, height) : structures;
    const transportLine = /^N1L_A(?:001|002|003|015|017)/.test(layers[layer].id);
    let visibleParts =
      !plan && transportLine && transport?.groundCuts
        ? parts.flatMap((part) =>
            transport.groundCuts!.line(
              part,
              false,
              layers[layer].id.slice(4, 8) === 'A003' ? 'SIDEWALK_AREA' : 'ROAD_AREA'
            )
          )
        : parts;
    if (!plan && transportLine && transport?.tunnelCuts)
      visibleParts = visibleParts.flatMap((p) => transport.tunnelCuts!.line(p));
    const code = layers[layer].id.slice(4, 8);
    // 원 포장 면이 있는 구간에 중심선 고정 폭 포장을 다시 만들지 않는다.
    if (!plan && (code === 'A002' || code === 'A003'))
      visibleParts = visibleParts.flatMap((p) =>
        (code === 'A002' ? roadCoverage : sidewalkCoverage).line(p)
      );
    for (const part of visibleParts) {
      if (plan) group(layer).lines.push(path(part));
      if (plan) continue;
      if (writer.line(layers[layer].id, part, color)) continue;
      for (let i = 1; i < part.length; i++)
        for (const segment of drapeSegment(part[i - 1], part[i], terrain))
          for (const point of segment) {
            lines.push(
              point[0],
              (height?.(point) ?? terrainMeshHeight(terrain, point)) + 0.09,
              -point[1]
            );
            lineColors.push(color.r, color.g, color.b);
          }
    }
  }
  for (const [layer, fid, polygons] of tile.areas) {
    if (structuresLoaded && !plan && bridgeStairFids.has(fid)) continue;
    // 교량 전용 레이어가 소유한 원 상판은 일반 지면 레이어에 다시 그리지 않는다.
    if (
      structuresLoaded &&
      !plan &&
      ['BRIDGE_AREA', 'PEDESTRIAN_OVERPASS_AREA', 'GRADE_SEPARATED_INTERSECTION_AREA'].includes(
        layers[layer].role
      )
    )
      continue;
    if (!plan && transport?.tunnelCuts && layers[layer].role === 'TUNNEL_AREA') continue;
    const color = style[layer];
    const transportArea = [
      'ROAD_AREA',
      'SIDEWALK_AREA',
      'RAILWAY_AREA',
      'INTERSECTION_AREA',
      'INTERCHANGE_AREA',
      'CROSSWALK_AREA',
      'TRAFFIC_SAFETY_AREA',
    ].includes(layers[layer].role);
    let visiblePolygons =
      !plan && transportArea && transport?.groundCuts
        ? transport.groundCuts.surface(polygons, layers[layer].role, fid)
        : polygons;
    if (!plan && transportArea && layers[layer].role !== 'RAILWAY_AREA' && transport?.tunnelCuts)
      visiblePolygons = transport.tunnelCuts.surface(visiblePolygons);
    if (!plan && ['INTERSECTION_AREA', 'INTERCHANGE_AREA'].includes(layers[layer].role))
      visiblePolygons = roadCoverage.surface(visiblePolygons);
    for (const polygon of visiblePolygons) {
      if (plan)
        group(layer)[styles[layer].fill ? 'areas' : 'lines'].push(
          polygon.map((ring) => path(ring, true)).join('')
        );
      if (plan) continue;
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
      if (
        !['ROAD_AREA', 'INTERSECTION_AREA', 'INTERCHANGE_AREA', 'SIDEWALK_AREA'].includes(
          layers[layer].role
        )
      )
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
