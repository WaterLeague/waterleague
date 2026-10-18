import {
  BoxGeometry,
  CylinderGeometry,
  ConeGeometry,
  Float32BufferAttribute,
  Color,
  type BufferGeometry,
} from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import type { InfrastructureAsset } from '../entity/infrastructure';

// 정규화된 시설 기호이며 치수·부피·펌프 호기 수의 물리 입력으로 사용하지 않는다.
export function infrastructureSymbolGeometry(kind: InfrastructureAsset['kind']): BufferGeometry {
  const parts: BufferGeometry[] = [];
  function part(g: BufferGeometry, color: string, x = 0, y = 0, z = 0, rotateZ = 0) {
    const geometry = g.index ? g.toNonIndexed() : g;
    if (geometry !== g) g.dispose();
    geometry.deleteAttribute('uv');
    geometry.rotateZ(rotateZ).translate(x, y, z);
    const rgb = new Color(color),
      count = geometry.getAttribute('position').count;
    geometry.setAttribute(
      'color',
      new Float32BufferAttribute(Array.from({ length: count }, () => rgb.toArray()).flat(), 3)
    );
    parts.push(geometry);
  }
  const box = (w: number, h: number, d: number, color: string, x = 0, y = h / 2, z = 0) =>
    part(new BoxGeometry(w, h, d), color, x, y, z);
  const cylinder = (r: number, h: number, color: string, x = 0, y = h / 2, z = 0, rotation = 0) =>
    part(new CylinderGeometry(r, r, h, 10), color, x, y, z, rotation);
  box(1.8, 0.15, 1.35, '#7d989d');
  if (kind === 'STORM_PUMP') {
    box(0.85, 0.95, 1.1, '#467b9d', -0.38, 0.62);
    cylinder(0.3, 0.9, '#b8dfe8', 0.43, 0.6, 0, Math.PI / 2);
    cylinder(0.14, 0.9, '#d8e9e8', 0.78, 1.06);
    cylinder(0.14, 0.6, '#d8e9e8', 0.6, 1.45, 0, Math.PI / 2);
  } else if (kind === 'RAINWATER_REUSE') {
    cylinder(0.6, 1.25, '#77aeb8', 0, 0.75);
    cylinder(0.64, 0.12, '#d1e8e5', 0, 1.4);
    cylinder(0.13, 0.45, '#d1e8e5', 0.65, 0.35, 0, Math.PI / 2);
  } else if (kind === 'INFILTRATION_PIT') {
    cylinder(0.55, 0.5, '#9bb9bf', 0, 0.38);
    for (let i = -2; i <= 2; i++) box(0.08, 0.1, 0.9, '#355b69', i * 0.2, 0.68);
  } else if (kind === 'INFILTRATION_GUTTER' || kind === 'INFILTRATION_TRENCH') {
    box(1.55, 0.22, 0.65, '#547887', 0, 0.22);
    for (let i = -3; i <= 3; i++) box(0.1, 0.14, 0.7, '#c3d5d4', i * 0.2, 0.4);
    if (kind === 'INFILTRATION_TRENCH')
      for (let i = -2; i <= 2; i++) cylinder(0.13, 0.15, '#a3a49e', i * 0.3, 0.27, 0.5);
  } else {
    box(1.5, 0.16, 1.05, kind === 'RETENTION_BASIN' ? '#72bccc' : '#80a56c', 0, 0.2);
    for (const [x, z] of [
      [-0.65, -0.4],
      [0.65, -0.4],
      [0.65, 0.4],
    ])
      part(new ConeGeometry(0.22, 0.6, 5), '#4e7656', x, 0.57, z);
    if (kind === 'INFILTRATION_OTHER') cylinder(0.3, 0.25, '#b7d2d0', 0, 0.4);
    if (kind === 'RAINWATER_FACILITY') box(0.4, 0.4, 0.4, '#a5ced3', -0.3, 0.45);
  }
  const result = mergeGeometries(parts)!;
  parts.forEach((g) => g.dispose());
  result.computeBoundingSphere();
  return result;
}
