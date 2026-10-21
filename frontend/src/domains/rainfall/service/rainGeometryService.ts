import { BufferAttribute, BufferGeometry, LineBasicMaterial } from 'three';
import type { rainParticleSeeds } from './rainEffectService';

type RainSeed = ReturnType<typeof rainParticleSeeds>[number] & { elevation: number };
export function createRainGeometry(seeds: RainSeed[], length: number) {
  const geometry = new BufferGeometry();
  const positions = new Float32Array(seeds.length * 6);
  const phases = new Float32Array(seeds.length * 2);
  seeds.forEach(({ point: [x, y], phase, elevation }, i) => {
    positions.set([x, elevation + length, -y, x, elevation, -y], i * 6);
    phases.fill(phase, i * 2, i * 2 + 2);
  });
  geometry.setAttribute('position', new BufferAttribute(positions, 3));
  geometry.setAttribute('rainPhase', new BufferAttribute(phases, 1));
  return geometry;
}
export function createRainMaterial() {
  const uniforms = { rainCycle: { value: 0 }, rainHeight: { value: 120 } };
  const material = new LineBasicMaterial({
    color: '#365f75',
    transparent: true,
    opacity: 0.65,
    depthWrite: false,
  });
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader =
      'attribute float rainPhase; uniform float rainCycle; uniform float rainHeight;\n' +
      shader.vertexShader.replace(
        '#include <begin_vertex>',
        '#include <begin_vertex>\ntransformed.y += rainHeight * (1.0 - fract(rainCycle + rainPhase));'
      );
  };
  material.customProgramCacheKey = () => 'waterleague-rain-gpu-v1';
  return { material, uniforms };
}
