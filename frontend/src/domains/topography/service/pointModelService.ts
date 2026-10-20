export type PointModelKind =
  | 'TREE'
  | 'LAMP'
  | 'SIGNAL'
  | 'UTILITY_POLE'
  | 'HYDRANT'
  | 'BUS_STOP'
  | 'WELL'
  | 'FOUNTAIN'
  | 'GRAVE'
  | 'MONUMENT'
  | 'PAGODA'
  | 'STATUE'
  | 'PHONE'
  | 'POSTBOX'
  | 'PLAYGROUND'
  | 'SIGN'
  | 'BARRIER'
  | 'CHIMNEY'
  | 'HELIPAD'
  | 'SURVEY'
  | 'FISHING'
  | 'STOCKPILE'
  | 'OBSERVATORY'
  | 'MIRROR'
  | 'TOLL'
  | 'WATERFALL'
  | 'FLOW';
const kinds: Record<string, PointModelKind> = {
  A013: 'BUS_STOP',
  A014: 'BUS_STOP',
  C009: 'WELL',
  C010: 'WELL',
  C011: 'FOUNTAIN',
  C012: 'WELL',
  C014: 'FISHING',
  C020: 'STOCKPILE',
  C022: 'LAMP',
  C023: 'UTILITY_POLE',
  C025: 'HYDRANT',
  C026: 'OBSERVATORY',
  C028: 'GRAVE',
  C031: 'MONUMENT',
  C033: 'MONUMENT',
  C034: 'PAGODA',
  C035: 'STATUE',
  C036: 'PHONE',
  C037: 'POSTBOX',
  C038: 'PLAYGROUND',
  C040: 'SIGN',
  C041: 'SIGN',
  C048: 'CHIMNEY',
  C049: 'SIGNAL',
  C050: 'BARRIER',
  C051: 'MIRROR',
  C054: 'TOLL',
  C055: 'HELIPAD',
  D003: 'TREE',
  E004: 'FLOW',
  E007: 'WATERFALL',
  F002: 'SURVEY',
};
export function pointModelKind(layerId: string): PointModelKind | null {
  return kinds[layerId.slice(4, 8)] ?? null;
}
export function modelMatrix(x: number, y: number, z: number, angle: number, scale = 1) {
  const c = Math.cos(angle) * scale,
    s = Math.sin(angle) * scale;
  return [c, 0, -s, 0, 0, scale, 0, 0, s, 0, c, 0, x, y, z, 1];
}
