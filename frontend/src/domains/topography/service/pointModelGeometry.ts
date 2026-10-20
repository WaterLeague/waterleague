import {
  BoxGeometry,
  BufferGeometry,
  Color,
  CylinderGeometry,
  Float32BufferAttribute,
  IcosahedronGeometry,
  MeshStandardMaterial,
  SphereGeometry,
  TorusGeometry,
} from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import type { PointModelKind } from './pointModelService';
type Model = { geometry: BufferGeometry; material: MeshStandardMaterial };
const cache = new Map<string, Model>();
export function pointModelGeometry(kind: PointModelKind, coarse: boolean): Model {
  const key = kind + ':' + coarse,
    cached = cache.get(key);
  if (cached) return cached;
  const parts: BufferGeometry[] = [];
  const add = (
    geometry: BufferGeometry,
    x: number,
    y: number,
    z: number,
    color: string,
    rotation?: [number, number, number]
  ) => {
    if (rotation) {
      geometry.rotateX(rotation[0]);
      geometry.rotateY(rotation[1]);
      geometry.rotateZ(rotation[2]);
    }
    geometry.translate(x, y, z);
    const c = new Color(color),
      values = new Float32Array(geometry.getAttribute('position').count * 3);
    for (let i = 0; i < values.length; i += 3) values.set([c.r, c.g, c.b], i);
    geometry.setAttribute('color', new Float32BufferAttribute(values, 3));
    geometry.setAttribute(
      'sourceLamp',
      new Float32BufferAttribute(
        new Float32Array(geometry.getAttribute('position').count).fill(
          kind === 'LAMP' && color === '#efe6ba' ? 1 : 0
        ),
        1
      )
    );
    const part = geometry.index ? geometry.toNonIndexed() : geometry;
    parts.push(part);
    if (part !== geometry) geometry.dispose();
  };
  const box = (w: number, h: number, d: number, x: number, y: number, z: number, color: string) =>
    add(new BoxGeometry(w, h, d), x, y, z, color);
  const pole = (h: number, r: number, x = 0, z = 0, color = '#929b96') =>
    add(new CylinderGeometry(r, r, h, coarse ? 5 : 8), x, h / 2, z, color);
  const crown = (r: number, x: number, y: number, z: number, color: string) =>
    add(new IcosahedronGeometry(r, 0), x, y, z, color);
  if (kind === 'TREE') {
    pole(3.2, 0.15, 0, 0, '#786650');
    if (coarse) crown(1.8, 0, 4, 0, '#638858');
    else {
      crown(1.65, 0, 4.5, 0, '#638858');
      crown(1.4, -0.8, 3.6, 0.2, '#77975f');
      crown(1.3, 0.8, 3.7, -0.25, '#557d4d');
    }
  } else if (kind === 'LAMP' || kind === 'UTILITY_POLE' || kind === 'SIGNAL') {
    const height = kind === 'UTILITY_POLE' ? 8 : kind === 'LAMP' ? 6.5 : 5.5;
    pole(height, 0.09);
    if (kind === 'UTILITY_POLE') {
      box(2, 0.12, 0.12, 0, height - 0.5, 0, '#656c69');
      for (const x of [-0.7, 0, 0.7])
        add(new CylinderGeometry(0.055, 0.055, 0.35, 6), x, height - 0.3, 0, '#c1c5b8');
    } else if (kind === 'LAMP') {
      box(1.7, 0.08, 0.09, 0.8, height, 0, '#7c8782');
      box(0.65, 0.12, 0.32, 1.45, height - 0.08, 0, '#efe6ba');
    } else {
      box(2.8, 0.09, 0.09, 1.3, height, 0, '#626f6b');
      box(0.32, 0.95, 0.24, 2.3, height - 0.45, 0, '#303f3b');
      for (const [i, color] of ['#a65342', '#c3a853', '#6b9872'].entries())
        add(
          new CylinderGeometry(0.095, 0.095, 0.035, 8),
          2.3,
          height - 0.15 - i * 0.28,
          0.14,
          color,
          [Math.PI / 2, 0, 0]
        );
    }
  } else if (kind === 'HYDRANT') {
    pole(0.8, 0.12, 0, 0, '#ab4d3b');
    add(new SphereGeometry(0.14, 8, 4), 0, 0.8, 0, '#bd6548');
    box(0.45, 0.14, 0.14, 0, 0.58, 0, '#a84332');
  } else if (kind === 'BUS_STOP' || kind === 'SIGN') {
    pole(2.5, 0.045);
    box(
      kind === 'BUS_STOP' ? 0.65 : 1.15,
      0.7,
      0.06,
      0,
      2.1,
      0,
      kind === 'BUS_STOP' ? '#4b7d72' : '#65756a'
    );
    box(0.45, 0.08, 0.07, 0, 2.15, 0.04, '#dfe7d2');
  } else if (kind === 'WELL' || kind === 'FOUNTAIN') {
    add(
      new CylinderGeometry(
        kind === 'WELL' ? 0.65 : 1.7,
        kind === 'WELL' ? 0.7 : 1.8,
        0.3,
        coarse ? 8 : 16
      ),
      0,
      0.15,
      0,
      '#9b9e91'
    );
    add(
      new CylinderGeometry(
        kind === 'WELL' ? 0.48 : 1.45,
        kind === 'WELL' ? 0.48 : 1.45,
        0.04,
        coarse ? 8 : 16
      ),
      0,
      0.32,
      0,
      '#7da5ac'
    );
    if (kind === 'WELL') pole(0.8, 0.06, 0, 0, '#717e76');
  } else if (kind === 'GRAVE') {
    box(0.8, 0.12, 1.3, 0, 0.06, 0, '#a9aca0');
    box(0.45, 0.6, 0.12, 0, 0.4, -0.4, '#8c938b');
  } else if (kind === 'MONUMENT' || kind === 'PAGODA' || kind === 'STATUE') {
    box(1.3, 0.4, 1.3, 0, 0.2, 0, '#9ca092');
    if (kind === 'PAGODA')
      for (let i = 0; i < 3; i++) {
        const w = 1.35 - i * 0.25;
        box(w, 0.18, w, 0, 0.7 + i * 0.7, 0, '#8e988b');
        box(w * 0.5, 0.5, w * 0.5, 0, 0.95 + i * 0.7, 0, '#a8aea0');
      }
    else if (kind === 'STATUE') {
      pole(1, 0.19, 0, 0, '#63756b');
      crown(0.23, 0, 1.5, 0, '#63756b');
      box(0.6, 0.12, 0.2, 0, 1.15, 0, '#63756b');
    } else box(0.65, 1.8, 0.35, 0, 1.2, 0, '#8f998d');
  } else if (kind === 'PHONE') {
    for (const x of [-0.4, 0.4]) for (const z of [-0.4, 0.4]) pole(2.1, 0.045, x, z, '#6a8178');
    box(0.9, 0.15, 0.9, 0, 2.1, 0, '#718d82');
    box(0.7, 1.4, 0.04, 0, 1.1, -0.4, '#a8c0b5');
    box(0.3, 0.5, 0.2, 0, 1.15, -0.25, '#61716c');
  } else if (kind === 'POSTBOX') {
    pole(0.8, 0.09, 0, 0, '#a14e3f');
    box(0.5, 0.65, 0.35, 0, 1, 0, '#b55b46');
    box(0.28, 0.04, 0.02, 0, 1.14, 0.185, '#4e5954');
  } else if (kind === 'PLAYGROUND') {
    for (const x of [-1, 1]) pole(2.1, 0.06, x, 0, '#6f8c73');
    box(2.2, 0.12, 0.12, 0, 2.1, 0, '#a58d5a');
    for (const x of [-0.25, 0.25])
      add(new CylinderGeometry(0.012, 0.012, 1.5, 5), x, 1.3, 0, '#65746c');
    box(0.7, 0.08, 0.4, 0, 0.55, 0, '#a08b58');
  } else if (kind === 'BARRIER') {
    box(0.25, 1, 0.25, 0, 0.5, 0, '#9c9f8d');
    box(2.5, 0.1, 0.1, 1.1, 0.9, 0, '#d7cab0');
  } else if (kind === 'CHIMNEY') {
    pole(5, 0.35, 0, 0, '#a5a396');
    add(new TorusGeometry(0.36, 0.06, 4, 8), 0, 5, 0, '#7b857a', [Math.PI / 2, 0, 0]);
  } else if (kind === 'FISHING') {
    box(1.5, 0.15, 1, 0, 0.08, 0, '#93866a');
    pole(1, 0.025, 0, 0, '#6d7766');
    add(new CylinderGeometry(0.018, 0.018, 2, 5), 0.55, 1.4, 0, '#7f745a', [0, 0, -0.55]);
  } else if (kind === 'STOCKPILE') {
    box(1.6, 0.15, 1.4, 0, 0.08, 0, '#9c8f76');
    for (const [x, z] of [
      [-0.4, -0.3],
      [0.4, -0.3],
      [0, 0.35],
    ])
      box(0.7, 0.65, 0.6, x, 0.5, z, '#a69c88');
  } else if (kind === 'OBSERVATORY') {
    box(0.75, 1.5, 0.6, 0, 0.75, 0, '#b9c3b6');
    pole(3, 0.045, 1, 0, '#85988e');
    box(0.9, 0.05, 0.12, 1, 2.8, 0, '#86968d');
  } else if (kind === 'MIRROR') {
    pole(2.5, 0.05, 0, 0, '#a67e59');
    add(new CylinderGeometry(0.4, 0.4, 0.07, coarse ? 8 : 16), 0, 2.4, 0, '#c2cfca', [
      Math.PI / 2,
      0,
      0,
    ]);
    add(new TorusGeometry(0.4, 0.045, 4, coarse ? 8 : 16), 0, 2.4, 0.04, '#bd814e');
  } else if (kind === 'TOLL') {
    box(1.5, 2.1, 1.5, 0, 1.05, 0, '#94a899');
    box(4, 0.2, 2.4, 0, 2.3, 0, '#7a9b89');
    box(1, 0.5, 0.03, 0, 1.5, 0.77, '#a9c4bd');
  } else if (kind === 'WATERFALL') {
    box(2.2, 0.6, 0.7, 0, 0.3, -0.4, '#9b9b86');
    box(1.5, 1.6, 0.12, 0, 0.8, 0, '#8fbcc3');
    box(2, 0.06, 1, 0, 0.04, 0.5, '#81abb4');
  } else if (kind === 'FLOW') {
    // 유수방향은 실물 시설이 아니므로 수면에 얇은 기준 형상으로 표시한다.
    box(0.08, 0.025, 0.8, 0, 0.02, 0, '#6e9fa7');
    box(0.45, 0.025, 0.08, 0, 0.02, -0.35, '#6e9fa7');
  } else if (kind === 'HELIPAD') {
    add(new CylinderGeometry(3, 3, 0.04, 16), 0, 0.03, 0, '#9cae95');
    box(2.4, 0.045, 0.18, 0, 0.07, 0, '#e5e7cd');
    for (const x of [-1.1, 1.1]) box(0.18, 0.045, 2.2, x, 0.07, 0, '#e5e7cd');
  } else add(new CylinderGeometry(0.12, 0.12, 0.04, 6), 0, 0.025, 0, '#7c8c80');
  const geometry = mergeGeometries(parts)!;
  parts.forEach((part) => part.dispose());
  geometry.computeBoundingSphere();
  const model = {
    geometry,
    material: new MeshStandardMaterial({ vertexColors: true, roughness: 0.9 }),
  };
  if (kind === 'LAMP') {
    const night = { value: 0 };
    model.material.userData.night = night;
    model.material.emissive.set('#ffe0a2');
    model.material.onBeforeCompile = (shader) => {
      shader.uniforms.sourceLampNight = night;
      shader.vertexShader =
        'attribute float sourceLamp; varying float vSourceLamp;\n' + shader.vertexShader;
      shader.vertexShader = shader.vertexShader.replace(
        '#include <begin_vertex>',
        '#include <begin_vertex>\nvSourceLamp=sourceLamp;'
      );
      shader.fragmentShader =
        'varying float vSourceLamp; uniform float sourceLampNight;\n' + shader.fragmentShader;
      shader.fragmentShader = shader.fragmentShader.replace(
        '#include <emissivemap_fragment>',
        '#include <emissivemap_fragment>\ntotalEmissiveRadiance*=vSourceLamp*sourceLampNight*2.;'
      );
    };
    model.material.customProgramCacheKey = () => 'source-lamp-v1';
  }
  cache.set(key, model);
  return model;
}
if (import.meta.hot)
  import.meta.hot.dispose(() => {
    for (const model of cache.values()) {
      model.geometry.dispose();
      model.material.dispose();
    }
    cache.clear();
  });
