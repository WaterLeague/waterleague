import { useEffect, useMemo } from 'react';
import { Color, Float32BufferAttribute, Shape, ShapeGeometry } from 'three';
import type { InfrastructureAsset } from '../../infrastructure/entity/infrastructure';
import { infrastructureSymbolGeometry } from '../../infrastructure/service/infrastructureShapeService';
import { WaterMaterial } from '../../surface/view/WaterMaterial';
import { useWaterObject } from '../../surface/view/WaterScene';
import { traceColor } from '../../floodtrace/service/floodTraceService';

export function HomeInfrastructureSymbol({ kind }: { kind: InfrastructureAsset['kind'] }) {
  const geometry = useMemo(() => infrastructureSymbolGeometry(kind), [kind]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial
        vertexColors
        color={kind === 'STORM_PUMP' ? '#a94f25' : '#b85b2b'}
        emissive="#b85b2b"
        emissiveIntensity={0.45}
        roughness={0.85}
        toneMapped={false}
      />
    </mesh>
  );
}

export function HomeFloodRecord() {
  const water = useWaterObject();
  const geometry = useMemo(() => {
    // 기록 표시를 설명하는 평면 모형이며 실제 사건 도형·침수심이 아니다.
    const shape = new Shape();
    shape.moveTo(-2.4, -1.6);
    for (const [x, y] of [
      [0.4, -1.6],
      [1.2, -0.9],
      [2.4, -0.7],
      [2.4, 0.3],
      [0.4, 0.3],
      [-0.6, -0.1],
      [-2.4, -0.1],
    ])
      shape.lineTo(x, y);
    shape.closePath();
    const result = new ShapeGeometry(shape).rotateX(-Math.PI / 2).translate(0, 0.075, 0);
    const count = result.getAttribute('position').count;
    const color = new Color(traceColor);
    const colors = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) color.toArray(colors, i * 3);
    result.setAttribute('color', new Float32BufferAttribute(colors, 3));
    result.setAttribute('flow', new Float32BufferAttribute(new Float32Array(count * 2), 2));
    result.setAttribute('waterDepth', new Float32BufferAttribute(new Float32Array(count), 1));
    result.setAttribute(
      'waterFace',
      new Float32BufferAttribute(new Float32Array(count).fill(1), 1)
    );
    return result;
  }, []);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <mesh ref={water} geometry={geometry}>
      <WaterMaterial record />
    </mesh>
  );
}
