import { expect, test } from 'vitest';
import { ShaderLib } from 'three';
import { createRainGeometry, createRainMaterial } from './rainGeometryService';
test('고정 빗방울 버퍼와 GPU 낙하가 원 위치·길이·주기를 유지', () => {
  const seeds = [{ point: [1500, -2700] as [number, number], phase: 0.37, elevation: 85 }];
  const geometry = createRainGeometry(seeds, 30),
    positions = geometry.getAttribute('position'),
    phases = geometry.getAttribute('rainPhase');
  expect(positions.count).toBe(2);
  const snapshot = Array.from(positions.array);
  for (const time of [0, 0.5, 21.3, 86400]) {
    const height = 900,
      cycle = (time / 1.7) % 1;
    const top = positions.getY(1) + height * (1 - ((cycle + phases.getX(1)) % 1));
    const previous = seeds[0].elevation + height * (1 - ((time / 1.7 + seeds[0].phase) % 1));
    expect(top).toBeCloseTo(previous, 3);
    expect(positions.getY(0) - positions.getY(1)).toBe(30);
  }
  expect(Array.from(positions.array)).toEqual(snapshot);
  const { material, uniforms } = createRainMaterial();
  const shader = {
    uniforms: {},
    vertexShader: ShaderLib.basic.vertexShader,
    fragmentShader: ShaderLib.basic.fragmentShader,
  };
  material.onBeforeCompile(shader as Parameters<typeof material.onBeforeCompile>[0], null!);
  expect(shader.vertexShader).toContain('transformed.y += rainHeight');
  expect(shader.uniforms).toMatchObject(uniforms);
  expect(material.opacity).toBe(0.65);
  expect(material.depthWrite).toBe(false);
  geometry.dispose();
  material.dispose();
});
