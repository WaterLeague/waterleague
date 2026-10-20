import {
  BoxGeometry,
  ConeGeometry,
  Color,
  Float32BufferAttribute,
  type BufferGeometry,
} from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import type { FacilityType } from '../../game/entity/game';
import { CatalogError } from '../exception/CatalogError';

export const facilitySymbolPaths: Record<FacilityType, string[]> = {
  RAINWATER_CISTERN: ['M-.8 -.7 H.8 V.7 H-.8 Z', 'M-.8 -.4 H.8 M.8 .4 H1.2 V.8'],
  RAIN_GARDEN: [
    'M-1 .7 Q-1.2 -.6 0 -.65 Q1.2 -.6 1 .7 Z',
    'M-.55 .15 L-.3 -.65 L0 .15 Z M.1 .3 L.4 -.4 L.7 .3 Z',
  ],
  PERMEABLE_PAVEMENT: [
    'M-1 -.65 H1 V.65 H-1 Z',
    'M-1 0 H1 M-.35 -.65 V0 M.35 -.65 V0 M-.65 0 V.65 M0 0 V.65 M.65 0 V.65',
  ],
  GREEN_ROOF: [
    'M-1 -.5 H1 V.75 H-1 Z',
    'M-1 -.5 L-.55 -1 H.55 L1 -.5 Z M-.65 0 V.45 M0 0 V.45 M.65 0 V.45',
  ],
  BIORETENTION: [
    'M-1 -.6 H1 V.75 H-1 Z',
    'M-1 .1 H1 M-1 .4 H1 M-.6 -.2 L-.3 -.95 L0 -.2 Z M.15 -.2 L.45 -.8 L.75 -.2 Z',
  ],
  VEGETATIVE_SWALE: [
    'M-1 -.7 L-.4 -.3 H.4 L1 -.7 V.7 L.4 .3 H-.4 L-1 .7 Z',
    'M-.8 -.45 L-.55 -.8 M.55 .55 L.8 .9',
  ],
  INFILTRATION_TRENCH: [
    'M-1 -.4 H1 V.4 H-1 Z',
    'M-.7 -.2 L-.45 .15 L-.2 -.2 L.05 .15 L.3 -.2 L.55 .15 L.8 -.2',
  ],
};

// 원본 경계가 없는 축척에서는 종류만 나타내며 실제 크기·층두께·배수 입력을 만들지 않는다.
export function facilitySymbolGeometry(type: FacilityType) {
  if (!facilitySymbolPaths[type]) throw new CatalogError('INVALID_DATA');
  const parts: BufferGeometry[] = [];
  function add(raw: BufferGeometry, color: string, x: number, y: number, z: number) {
    const geometry = raw.toNonIndexed();
    raw.dispose();
    geometry.deleteAttribute('uv');
    geometry.translate(x, y, z);
    const rgb = new Color(color),
      count = geometry.getAttribute('position').count;
    const colors = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) rgb.toArray(colors, i * 3);
    geometry.setAttribute('color', new Float32BufferAttribute(colors, 3));
    parts.push(geometry);
  }
  const box = (w: number, h: number, d: number, color: string, x = 0, y = h / 2, z = 0) =>
    add(new BoxGeometry(w, h, d), color, x, y, z);
  const plant = (x: number, z: number, base: number, height = 0.65) =>
    add(new ConeGeometry(0.22, height, 5), '#4b7843', x, base + height / 2, z);
  if (type === 'RAINWATER_CISTERN') {
    box(1.4, 1.3, 1.1, '#548eae');
    box(1.5, 0.12, 1.2, '#b2c8d4', 0, 1.36);
    box(0.5, 0.12, 0.12, '#7b929f', 0.85, 0.2);
  } else if (type === 'PERMEABLE_PAVEMENT') {
    box(2, 0.12, 1.4, '#567e89');
    for (let x = 0; x < 4; x++)
      for (let z = 0; z < 3; z++)
        box(
          0.44,
          0.12,
          0.39,
          (x + z) % 2 ? '#b2c7c9' : '#8da9ad',
          x * 0.49 - 0.735,
          0.18,
          z * 0.44 - 0.44
        );
  } else if (type === 'INFILTRATION_TRENCH') {
    box(2, 0.3, 0.65, '#64718a');
    for (let i = 0; i < 7; i++)
      box(
        0.2,
        0.14,
        0.25,
        i % 2 ? '#bcc4cd' : '#8797a8',
        i * 0.26 - 0.78,
        0.36,
        i % 2 ? 0.1 : -0.1
      );
  } else if (type === 'VEGETATIVE_SWALE') {
    box(2, 0.12, 0.7, '#8b9c63');
    box(2, 0.28, 0.28, '#639452', 0, 0.2, -0.48);
    box(2, 0.28, 0.28, '#639452', 0, 0.2, 0.48);
    plant(-0.65, -0.48, 0.34, 0.35);
    plant(0.65, 0.48, 0.34, 0.35);
  } else {
    if (type === 'GREEN_ROOF') {
      box(1.8, 0.7, 1.3, '#b5c4bd');
      box(1.95, 0.16, 1.45, '#82a959', 0, 0.78);
      plant(-0.5, -0.3, 0.86, 0.35);
      plant(0.4, 0.3, 0.86, 0.35);
    } else if (type === 'BIORETENTION') {
      box(1.8, 0.25, 1.3, '#9ca6ac');
      box(1.8, 0.28, 1.3, '#92704b', 0, 0.39);
      box(1.8, 0.12, 1.3, '#6e9c67', 0, 0.59);
      plant(-0.5, -0.25, 0.65);
      plant(0.4, 0.25, 0.65);
    } else {
      box(1.9, 0.2, 1.4, '#a28c60');
      box(1.65, 0.12, 1.15, '#86a665', 0, 0.26);
      plant(-0.45, -0.2, 0.32);
      plant(0.45, 0.2, 0.32, 0.5);
    }
  }
  const geometry = mergeGeometries(parts);
  parts.forEach((part) => part.dispose());
  if (!geometry) throw new CatalogError('INVALID_DATA');
  geometry.computeBoundingSphere();
  return geometry;
}
