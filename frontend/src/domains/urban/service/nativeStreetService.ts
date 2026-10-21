import { connectNativeJunctions } from './nativeJunctionService';
import type { NativeBridgeGroup, NativeBridgeProfile } from '../dto/nativeBridgeDto';
import type { CityTile } from '../../city/entity/city';
import type { Street } from '../entity/urban';
import { nativeDeckLift as deckLift } from './nativeBridgeService';
import { NativeGroundCuts } from './nativeGroundCutService';
import { waterDeckBindings } from './nativeBridgeTransportService';
export function nativeSurfaceColor(role: string) {
  return role === 'SIDEWALK_AREA'
    ? '#b3ae9f'
    : role === 'CULTIVATION_LANDSCAPE_AREA'
      ? '#98aa8b'
      : role === 'RAILWAY_AREA'
        ? '#8b9292'
        : '#667071';
}
export function nativeStreets(
  tiles: Pick<CityTile, 'id' | 'nativeFeatures' | 'urban'>[],
  groups?: NativeBridgeGroup[],
  lanes?: Map<string, number>,
  widths?: Map<string, number>
): Street[] {
  groups = groups?.filter((g) => !g.kinds?.includes('지하차도'));
  const result: Street[] = [];
  const groundCuts =
    groups?.[0]?.displayWaterPolygons ?? groups?.flatMap((g) => g.groundCutPolygons ?? []);
  const waterCopies = new NativeGroundCuts([], groundCuts);
  const groundCopies = new NativeGroundCuts(groups ?? []);
  const walkingDecks = new Map<string, NonNullable<Street['nativeWalkingDecks']>>();
  const loadedWalkSources = new Set(
    tiles.flatMap((t) => t.urban?.walkPaths.map((p) => p.sourceObjectId) ?? [])
  );
  for (const group of groups ?? [])
    for (const sidewalk of group.sidewalks ?? []) {
      if (!walkingDecks.has(sidewalk.sourceId)) walkingDecks.set(sidewalk.sourceId, []);
      walkingDecks.get(sidewalk.sourceId)!.push({
        polygons: sidewalk.polygons,
        deckPolygons: group.displayDatumPolygons ?? group.polygons,
        deckLiftM: deckLift(group),
      });
      for (const approach of sidewalk.approaches ?? []) {
        const source = group.profiles[approach.profileIndex];
        if (source)
          walkingDecks.get(sidewalk.sourceId)!.push({
            polygons: approach.polygons,
            deckPolygons: group.displayDatumPolygons ?? group.polygons,
            profile: {
              ...source,
              deckPolygons: group.displayDatumPolygons ?? group.polygons,
              deckLiftM: deckLift(group),
            },
          });
      }
    }
  const profileByRoad = new Map<string, NativeBridgeProfile[]>();
  for (const group of groups ?? [])
    for (const profile of group.profiles) {
      const value = {
        ...profile,
        deckPolygons: group.displayDatumPolygons ?? group.polygons,
        deckLiftM: deckLift(group),
      };
      for (const id of profile.roadIds) {
        if (!profileByRoad.has(id)) profileByRoad.set(id, []);
        profileByRoad.get(id)!.push(value);
      }
    }
  for (const tile of tiles) {
    const surfaces = tile.nativeFeatures
      .filter((f) => f.role === 'ROAD_AREA')
      .flatMap((f) =>
        f.geometry.type === 'Polygon'
          ? [f.geometry.coordinates]
          : f.geometry.type === 'MultiPolygon'
            ? f.geometry.coordinates
            : []
      );
    const areas = surfaces.map((p) => ({
      polygon: p,
      bounds: p[0].reduce(
        (b, q) => [
          Math.min(b[0], q[0]),
          Math.min(b[1], q[1]),
          Math.max(b[2], q[0]),
          Math.max(b[3], q[1]),
        ],
        [Infinity, Infinity, -Infinity, -Infinity]
      ),
    }));
    for (const feature of tile.nativeFeatures) {
      if (groups && feature.role === 'BRIDGE_AREA') continue;
      // 지표면은 전체 지형지물 타일이 한 번만 그려 건물 타일 제한과 면 중첩을 피한다.
      if (
        [
          'ROAD_AREA',
          'SIDEWALK_AREA',
          'TUNNEL_AREA',
          'RAILWAY_AREA',
          'CULTIVATION_LANDSCAPE_AREA',
          'RIVER_WATER_AREA',
          'LAKE_RESERVOIR_AREA',
          'RAIL_CENTERLINE',
        ].includes(feature.role)
      )
        continue;
      const base = {
        id: feature.id,
        class: feature.roadClass ?? feature.role,
        districtId: feature.districtId,
        widthM: 0,
        widthSource: 'NOT_CONFIRMED' as const,
        walk: false,
        motor: false,
        oneway: 0,
        sidewalk: '',
        bridge: feature.role === 'BRIDGE_AREA',
        nativeSourceRole: feature.role,
      };
      const geometry = feature.geometry;
      if (geometry.type === 'Polygon' || geometry.type === 'MultiPolygon') {
        const polygons =
          geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates;
        result.push({ ...base, coordinates: polygons[0][0], nativePolygons: polygons });
      } else if (feature.role === 'ROAD_CENTERLINE') {
        const parts =
          geometry.type === 'LineString' ? [geometry.coordinates] : geometry.coordinates;
        for (let index = 0; index < parts.length; index++) {
          const count = lanes?.get(feature.id);
          const sourceWidth = widths?.get(feature.id);
          const roadWidth = sourceWidth ?? (count ? count * 3.25 : 0);
          const coordinates = parts[index];
          const bounds = coordinates.reduce(
            (b, p) => [
              Math.min(b[0], p[0]),
              Math.min(b[1], p[1]),
              Math.max(b[2], p[0]),
              Math.max(b[3], p[1]),
            ],
            [Infinity, Infinity, -Infinity, -Infinity]
          );
          let length = 0;
          for (let j = 1; j < coordinates.length; j++)
            length += Math.hypot(
              coordinates[j][0] - coordinates[j - 1][0],
              coordinates[j][1] - coordinates[j - 1][1]
            );
          result.push({
            ...base,
            id: feature.id + ':part:' + index,
            coordinates: parts[index],
            widthM: roadWidth,
            widthSource: sourceWidth
              ? 'NGII_WIDTH_ATTRIBUTE'
              : count
                ? 'DISPLAY_ASSUMPTION'
                : 'NOT_CONFIRMED',
            lanes: count,
            motor:
              !!count &&
              count >= 2 &&
              feature.trafficDirection === 'BIDIRECTIONAL' &&
              feature.geometryEligibility === 'GEOMETRY_ONLY',
            nativeTrafficDirection: feature.trafficDirection ?? 'UNKNOWN',
            nativeBridgeProfiles: profileByRoad.get(feature.id + ':part:' + index),
            nativeGroundCutPolygons: groundCuts,
            nativeWaterDecks: waterDeckBindings(
              (groups ?? []).filter((g) =>
                g.profiles.some((p) => p.roadIds.includes(feature.id + ':part:' + index))
              ),
              coordinates
            ),
            nativeLaneClipPolygons: count
              ? areas
                  .filter(
                    (a) =>
                      a.bounds[0] <= bounds[2] + 30 &&
                      a.bounds[2] >= bounds[0] - 30 &&
                      a.bounds[1] <= bounds[3] + 30 &&
                      a.bounds[3] >= bounds[1] - 30
                  )
                  .map((a) => a.polygon)
              : undefined,
            nativeLanePaths: count
              ? [{ coordinates, lanes: count, widthM: roadWidth, span: [0, length] }]
              : undefined,
          });
        }
      }
    }
    for (const path of tile.urban?.walkPaths ?? [])
      result.push({
        id: path.id,
        districtId: path.districtId,
        coordinates: path.coordinates,
        class: 'footway',
        widthM: 0,
        widthSource: 'NOT_CONFIRMED',
        walk: true,
        motor: false,
        oneway: 0,
        sidewalk: '',
        bridge: false,
        nativeSourceRole: 'SIDEWALK_DISPLAY_PATH',
        nativeDisplayPath: true,
        nativeWalkingDecks: walkingDecks.get(path.sourceObjectId),
        nativeGroundCutPolygons: groundCuts,
        nativeWaterDecks: waterDeckBindings(
          (groups ?? []).filter((g) =>
            g.sidewalks?.some((s) => s.sourceId === path.sourceObjectId)
          ),
          path.coordinates
        ),
      });
    for (const crossing of tile.urban?.crosswalks ?? [])
      result.push({
        id: crossing.id,
        districtId: crossing.districtId,
        coordinates: crossing.polygons[0][0],
        class: 'footway',
        widthM: 0,
        widthSource: 'NOT_CONFIRMED',
        walk: false,
        motor: false,
        oneway: 0,
        sidewalk: '',
        bridge: false,
        nativeSourceRole: 'CROSSWALK_AREA',
        nativePolygons: groundCopies.surface(crossing.polygons, 'CROSSWALK_AREA'),
        nativeMarkingPolygons: groundCopies.surface(crossing.stripes, 'CROSSWALK_AREA'),
      });
  }
  for (const group of groups ?? []) {
    const common = {
      class: group.role,
      districtId: '',
      widthM: 0,
      widthSource: 'NOT_CONFIRMED' as const,
      walk: false,
      motor: false,
      oneway: 0,
      sidewalk: '',
      bridge: true,
      nativeDeckLiftM: deckLift(group),
      nativeDeckLevel: group.lowerDeck ? ('upper' as const) : undefined,
    };
    const integralAccess: NativeBridgeProfile[] = [];
    if (group.role === 'PEDESTRIAN_OVERPASS_AREA' && !group.profiles.some((p) => p.steps)) {
      const points = group.polygons.flatMap((p) => p[0]);
      let axis: [number, number] = [1, 0],
        longest = 0;
      for (const polygon of group.polygons)
        for (let i = 1; i < polygon[0].length; i++) {
          const a = polygon[0][i - 1],
            b = polygon[0][i],
            length = Math.hypot(b[0] - a[0], b[1] - a[1]);
          if (length > longest) {
            longest = length;
            axis = [(b[0] - a[0]) / length, (b[1] - a[1]) / length];
          }
        }
      const along = points.map((p) => p[0] * axis[0] + p[1] * axis[1]),
        across = points.map((p) => -p[0] * axis[1] + p[1] * axis[0]),
        start = Math.min(...along),
        end = Math.max(...along),
        middle = (Math.min(...across) + Math.max(...across)) / 2,
        length = end - start;
      if (length > 2) {
        const at = (v: number): [number, number] => [
            v * axis[0] - middle * axis[1],
            v * axis[1] + middle * axis[0],
          ],
          access = Math.min(8, length * 0.25);
        // 원본에 계단 면이 없는 육교는 자기 외곽 안의 양 끝에 표시 계단을 둔다.
        integralAccess.push({
          roadIds: [],
          coordinates: [at(start), at(end)],
          span: [access, length - access],
          polygons: group.polygons,
          displayWidthM: Math.max(...across) - Math.min(...across),
          steps: true,
          deckPolygons: group.displayDatumPolygons ?? group.polygons,
        });
      }
    }
    result.push({
      ...common,
      id: group.id,
      coordinates: group.polygons[0][0],
      nativeSourceRole: group.role,
      nativePolygons: group.outlinePolygons ?? group.polygons,
      bridgeName: group.names?.join(' · '),
      nativeUnderpassPolygons: group.preservedUnderpassPolygons,
      nativeBridgeGroupPolygons: group.displayDatumPolygons ?? group.polygons,
      nativeBridgeProfiles: integralAccess.length ? integralAccess : undefined,
      nativeStructurePath: group.profiles.length
        ? (() => {
            const profile = [...group.profiles].sort(
              (a, b) => b.span[1] - b.span[0] - (a.span[1] - a.span[0])
            )[0];
            return {
              coordinates: profile.coordinates,
              span: profile.span,
              widthM: profile.displayWidthM,
            };
          })()
        : undefined,
    });
    for (const [n, sidewalk] of (group.sidewalks ?? []).entries()) {
      result.push({
        ...common,
        id: group.id + ':sidewalk:' + n,
        coordinates: sidewalk.polygons[0][0],
        nativeSourceRole: 'SIDEWALK_AREA',
        nativePolygons: sidewalk.polygons,
        nativeBridgeGroupPolygons: group.displayDatumPolygons ?? group.polygons,
      });
      for (const [a, approach] of (sidewalk.approaches ?? []).entries()) {
        const source = group.profiles[approach.profileIndex];
        if (!source) continue;
        const profile = {
          ...source,
          deckPolygons: group.displayDatumPolygons ?? group.polygons,
          deckLiftM: deckLift(group),
        };
        result.push({
          ...common,
          bridge: false,
          id: group.id + ':sidewalk:' + n + ':approach:' + a,
          coordinates: source.coordinates,
          nativeSourceRole: 'SIDEWALK_AREA',
          nativePolygons: waterCopies.surface(approach.polygons),
          nativeBridgeProfiles: [profile],
        });
        if (!loadedWalkSources.has(sidewalk.sourceId))
          for (const [p, coordinates] of approach.paths.entries())
            result.push({
              ...common,
              bridge: false,
              walk: true,
              id: group.id + ':sidewalk:' + n + ':approach:' + a + ':walk:' + p,
              coordinates,
              nativeSourceRole: 'SIDEWALK_DISPLAY_PATH',
              nativeDisplayPath: true,
              nativeWalkingDecks: [
                { polygons: approach.polygons, deckPolygons: profile.deckPolygons, profile },
              ],
            });
      }
      if (!loadedWalkSources.has(sidewalk.sourceId))
        for (const [part, coordinates] of sidewalk.paths.entries())
          result.push({
            ...common,
            id: group.id + ':walk:' + n + ':' + part,
            coordinates,
            bridge: false,
            walk: true,
            nativeSourceRole: 'SIDEWALK_DISPLAY_PATH',
            nativeDisplayPath: true,
            nativeWalkingDecks: [
              {
                polygons: sidewalk.polygons,
                deckPolygons: group.displayDatumPolygons ?? group.polygons,
                deckLiftM: deckLift(group),
              },
            ],
          });
    }
    for (const [part, coordinates] of (group.walkPaths ?? []).entries())
      result.push({
        ...common,
        id: group.id + ':walk:' + part,
        coordinates,
        walk: true,
        nativeSourceRole: 'SIDEWALK_DISPLAY_PATH',
        nativeDisplayPath: true,
        nativeBridgeProfiles: integralAccess.length ? integralAccess : undefined,
        nativeWalkingDecks: integralAccess.length
          ? undefined
          : [
              {
                polygons: group.polygons,
                deckPolygons: group.displayDatumPolygons ?? group.polygons,
              },
            ],
      });
    group.profiles.forEach((profile, index) =>
      result.push({
        ...common,
        bridge: false,
        walk: profile.steps === true,
        id: group.id + ':approach:' + index,
        coordinates: profile.coordinates,
        nativeSourceRole: profile.rail ? 'RAILWAY_AREA' : 'BRIDGE_APPROACH',
        nativePolygons: waterCopies.surface(profile.polygons),
        nativeBridgeProfiles: [
          {
            ...profile,
            deckPolygons: group.displayDatumPolygons ?? group.polygons,
            deckLiftM: deckLift(group),
          },
        ],
      })
    );
    const lower = group.lowerDeck;
    if (lower) {
      const base = {
        ...common,
        nativeDeckLevel: 'lower' as const,
        nativeDeckLiftM: lower.deckLiftM,
        nativeBridgeGroupPolygons: group.displayDatumPolygons ?? group.polygons,
      };
      result.push({
        ...base,
        id: group.id + ':lower',
        coordinates: lower.polygons[0][0],
        nativeSourceRole: lower.rail ? 'RAILWAY_AREA' : 'ROAD_AREA',
        nativePolygons: lower.polygons,
        nativeRailPaths: lower.railPaths,
      });
      for (const [i, coordinates] of lower.railPaths.entries())
        result.push({
          ...base,
          id: group.id + ':lower:train:' + i,
          coordinates,
          nativeSourceRole: 'RAIL_DISPLAY_PATH',
          nativeRailKind: 'subway',
          nativeRailName: '지하철7호선',
          nativeWalkingDecks: [
            {
              polygons: lower.polygons,
              deckPolygons: group.displayDatumPolygons ?? group.polygons,
              deckLiftM: lower.deckLiftM,
            },
          ],
        });
      if (lower.sidewalks.length)
        result.push({
          ...base,
          id: group.id + ':lower:sidewalk',
          coordinates: lower.sidewalks[0][0],
          nativeSourceRole: 'SIDEWALK_AREA',
          nativePolygons: lower.sidewalks,
        });
      for (const [i, coordinates] of lower.walkPaths.entries())
        result.push({
          ...base,
          id: group.id + ':lower:walk:' + i,
          coordinates,
          walk: true,
          nativeSourceRole: 'SIDEWALK_DISPLAY_PATH',
          nativeDisplayPath: true,
          nativeWalkingDecks: [
            {
              polygons: lower.sidewalks,
              deckPolygons: group.displayDatumPolygons ?? group.polygons,
              deckLiftM: lower.deckLiftM,
            },
          ],
        });
      for (const [i, approach] of lower.approaches.entries())
        result.push({
          ...base,
          id: group.id + ':lower:approach:' + i,
          bridge: false,
          coordinates: approach.coordinates,
          nativeSourceRole: 'BRIDGE_APPROACH',
          nativePolygons: approach.polygons,
          nativeBridgeProfiles: [
            {
              ...approach,
              deckPolygons: group.displayDatumPolygons ?? group.polygons,
              deckLiftM: lower.deckLiftM,
            },
          ],
        });
    }
  }
  return connectNativeJunctions([...new Map(result.map((r) => [r.id, r])).values()]);
}
