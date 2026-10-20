import type { CisternSpecification } from '../../facility/dto/cisternSpecificationDto';
import { CISTERN_SPECIFICATIONS_HASH } from '../../facility/dto/cisternSpecificationDto';
import { cisternEquipmentRequestDto } from '../dto/cisternLayoutDto';
import type { MapPoint } from '../../catalog/entity/facilityFootprint';
import {
  facilityPolygonFootprint,
  polygonArea,
} from '../../catalog/service/facilityGeometryService';
import type {
  CisternEquipmentRequest,
  CisternEquipmentPreview,
  CisternGeometryPreview,
  CisternLayoutRequest,
} from '../dto/cisternLayoutDto';
import type { SharedSite } from '../entity/installation';
import { cisternLayoutRequestDto } from '../dto/cisternLayoutDto';
export type CisternLayoutFields = Record<'width' | 'wall' | 'east' | 'north' | 'rotation', string>;
export function parseCisternLayout(fields: CisternLayoutFields): CisternLayoutRequest | null {
  if (
    !/^\d+(\.\d{1,2})?$/.test(fields.width) ||
    !/^\d+(\.\d{1,3})?$/.test(fields.wall) ||
    !/^-?\d+(\.\d{1,3})?$/.test(fields.east) ||
    !/^-?\d+(\.\d{1,3})?$/.test(fields.north) ||
    !/^\d+(\.\d{1,2})?$/.test(fields.rotation)
  )
    return null;
  const parsed = cisternLayoutRequestDto.safeParse({
    widthM: Number(fields.width),
    wallThicknessM: Number(fields.wall),
    offsetXM: Number(fields.east),
    offsetYM: Number(fields.north),
    rotationDeg: Number(fields.rotation),
  });
  return parsed.success ? parsed.data : null;
}

function clip(points: MapPoint[], axis: number, bound: number, sign: number): MapPoint[] {
  const result: MapPoint[] = [];
  for (let i = 0; i < points.length; i++) {
    const a = points[i],
      b = points[(i + 1) % points.length];
    const insideA = sign * (a[axis] - bound) <= 0,
      insideB = sign * (b[axis] - bound) <= 0;
    if (insideA) result.push(a);
    if (insideA !== insideB) {
      const t = (bound - a[axis]) / (b[axis] - a[axis]);
      result.push([a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])]);
    }
  }
  return result;
}
export function cisternGeometry(
  ground: Pick<SharedSite, 'polygons' | 'center' | 'modelHash'>,
  area: number,
  depth: number,
  layout: CisternLayoutRequest
): CisternGeometryPreview | null {
  const { widthM: w, wallThicknessM: wall, rotationDeg: r, offsetXM: dx, offsetYM: dy } = layout;
  if (
    [area, depth, w, wall, r, dx, dy].some((v) => !Number.isFinite(v)) ||
    area <= 0 ||
    depth <= 0 ||
    w <= 0 ||
    wall <= 0 ||
    r < 0 ||
    r >= 360
  )
    return null;
  const length = area / w,
    ow = w + 2 * wall,
    ol = length + 2 * wall;
  const shape = rectangleGeometry(ground, ow, ol, r, dx, dy);
  if (!shape) return null;
  return {
    method: 'RECTANGULAR_INTERNAL_SECTION_WITH_WALL_V1',
    sourceModelHash: ground.modelHash,
    ...shape,
    internalWidthM: w,
    internalLengthM: length,
    wallThicknessM: wall,
    outerWidthM: ow,
    outerLengthM: ol,
    storageDepthM: depth,
    rotationDeg: r,
  };
}

function rectangleGeometry(
  ground: Pick<SharedSite, 'polygons' | 'center'>,
  ow: number,
  ol: number,
  r: number,
  dx: number,
  dy: number
) {
  const center: MapPoint = [ground.center[0] + dx, ground.center[1] + dy];
  const angle = (r * Math.PI) / 180,
    c = Math.cos(angle),
    s = Math.sin(angle);
  const local = ground.polygons.map((component) =>
    component.map((ring) =>
      ring.map(([x, y]): MapPoint => [
        c * (x - center[0]) + s * (y - center[1]),
        -s * (x - center[0]) + c * (y - center[1]),
      ])
    )
  );
  let covered: number;
  try {
    // 오목한 경계도 삼각형별 교차 면적을 합산해 네 꼭짓점만 들어가는 배치를 거부한다.
    covered = facilityPolygonFootprint(local, 1).polygons.reduce((sum, p) => {
      for (const [axis, bound, sign] of [
        [0, ow / 2, 1],
        [0, -ow / 2, -1],
        [1, ol / 2, 1],
        [1, -ol / 2, -1],
      ])
        p = clip(p, axis, bound, sign);
      return sum + (p.length >= 3 ? polygonArea(p) : 0);
    }, 0);
  } catch {
    return null;
  }
  const coordinates = [
    [-1, -1],
    [1, -1],
    [1, 1],
    [-1, 1],
  ].map(([a, b]): MapPoint => [
    center[0] + (c * a * ow) / 2 - (s * b * ol) / 2,
    center[1] + (s * a * ow) / 2 + (c * b * ol) / 2,
  ]);
  coordinates.push(coordinates[0]);
  return {
    center,
    coordinates,
    contained: Math.abs(ow * ol - covered) <= Math.max(1e-8, ow * ol * 1e-9),
  };
}

export function parseCisternEquipment(
  fields: CisternLayoutFields,
  specificationId: string
): CisternEquipmentRequest | null {
  if (
    !/^-?\d+(\.\d{1,3})?$/.test(fields.east) ||
    !/^-?\d+(\.\d{1,3})?$/.test(fields.north) ||
    !/^\d+(\.\d{1,2})?$/.test(fields.rotation)
  )
    return null;
  const parsed = cisternEquipmentRequestDto.safeParse({
    specificationId,
    catalogSha256: CISTERN_SPECIFICATIONS_HASH,
    offsetXM: Number(fields.east),
    offsetYM: Number(fields.north),
    rotationDeg: Number(fields.rotation),
  });
  return parsed.success ? parsed.data : null;
}
export function cisternEquipmentGeometry(
  ground: Pick<SharedSite, 'polygons' | 'center' | 'modelHash'>,
  spec: CisternSpecification,
  request: CisternEquipmentRequest
): CisternEquipmentPreview | null {
  if (
    !cisternEquipmentRequestDto.safeParse(request).success ||
    request.specificationId !== spec.id ||
    request.catalogSha256 !== CISTERN_SPECIFICATIONS_HASH
  )
    return null;
  const { width, length, height } = spec.equipmentDimensionsM;
  if ([width, length, height].some((v) => !Number.isFinite(v) || v <= 0)) return null;
  const shape = rectangleGeometry(
    ground,
    width,
    length,
    request.rotationDeg,
    request.offsetXM,
    request.offsetYM
  );
  return shape
    ? {
        ...shape,
        method: 'PUBLIC_EQUIPMENT_ENVELOPE_V1',
        sourceModelHash: ground.modelHash,
        specificationId: spec.id,
        catalogSha256: request.catalogSha256,
        widthM: width,
        lengthM: length,
        heightM: height,
        rotationDeg: request.rotationDeg,
      }
    : null;
}
