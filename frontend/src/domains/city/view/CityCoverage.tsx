import { useEffect, useMemo } from 'react';
import type { Terrain } from '../../terrain/entity/terrain';
import { useCityCoverage } from '../controller/useCityCoverage';
import { cityCoverageGeometry } from '../service/cityCoverageGeometry';

export function CityCoverage({ terrain, distance }: { terrain: Terrain | null; distance: number }) {
  const { areas } = useCityCoverage();
  const geometry = useMemo(() => cityCoverageGeometry(areas, terrain), [areas, terrain]);
  const uniforms = useMemo(() => ({ spacing: { value: 20 } }), []);
  useEffect(() => {
    uniforms.spacing.value = Math.max(12, Math.min(180, distance / 80));
  }, [uniforms, distance]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <mesh geometry={geometry} renderOrder={4} raycast={() => {}}>
      <shaderMaterial
        transparent
        depthWrite={false}
        uniforms={uniforms}
        vertexShader={
          'varying vec2 ground; void main(){ground=position.xz;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}'
        }
        fragmentShader={
          'uniform float spacing;varying vec2 ground;void main(){float stripe=step(.86,fract((ground.x+ground.y)/spacing));gl_FragColor=vec4(.38,.39,.36,.08+stripe*.3);}'
        }
      />
    </mesh>
  );
}
