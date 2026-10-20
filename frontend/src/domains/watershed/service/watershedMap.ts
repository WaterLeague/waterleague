import type { WatershedGeoreference } from '../dto/watershedGeoreferenceDto';
import type { City } from '../../city/entity/city';
export function watershedMap(profile: WatershedGeoreference, city: City) {
  if (profile.horizontalCrs !== city.coordinateSystem || profile.sourceCrsVerified !== false)
    throw new Error('관망 위치 기준 불일치');
  const point = ([x, y]: [number, number]): [number, number] => [
    x - city.originProjected[0],
    y - city.originProjected[1],
  ];
  const [x0, y0, x1, y1] = profile.bounds;
  return {
    id: profile.id,
    center: point([(x0 + x1) / 2, (y0 + y1) / 2]),
    distance: Math.max(x1 - x0, y1 - y0) * 1.8,
    nodes: profile.nodes.map((n) => ({ ...n, coordinate: point(n.coordinate) })),
    links: profile.links.map((l) => ({ ...l, points: l.points.map(point) })),
    catchments: profile.catchments.map((c) => ({ ...c, points: c.points.map(point) })),
  };
}
export type WatershedMap = ReturnType<typeof watershedMap>;
export type WatershedMapSelection = {
  map: WatershedMap;
  selectedId: string;
  disabled: boolean;
  onSelect: (id: string) => void;
};
