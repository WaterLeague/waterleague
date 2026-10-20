import type { TopographyIndex } from '../dto/topographyDto';
export function topographyStyle(layer: TopographyIndex['layers'][number]) {
  const boundary =
    ['ADMINISTRATIVE_AREA', 'RIVER_BOUNDARY_AREA'].includes(layer.role) ||
    /_(?:G0020000|H0010000)$/.test(layer.id);
  const road = [
    'INTERSECTION_AREA',
    'GRADE_SEPARATED_INTERSECTION_AREA',
    'INTERCHANGE_AREA',
  ].includes(layer.role);
  const colors: Record<string, string> = {
    ROAD_AREA: '#667071',
    SIDEWALK_AREA: '#b3ae9f',
    BUILDING_FOOTPRINT: '#d5d7ca',
    CULTIVATION_LANDSCAPE_AREA: '#98aa8b',
    RIVER_WATER_AREA: '#81b1ba',
    LAKE_RESERVOIR_AREA: '#81b1ba',
  };
  return { fill: !boundary, color: road ? '#667071' : (colors[layer.role] ?? layer.color) };
}
