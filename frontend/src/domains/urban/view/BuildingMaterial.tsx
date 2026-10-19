import { useEffect, useMemo } from 'react';
import { MeshStandardMaterial } from 'three';
import { useUrbanLighting } from './UrbanEnvironment';
export function BuildingMaterial({ opacity }: { opacity: number }) {
  const light = useUrbanLighting();
  const material = useMemo(() => {
    const value = new MeshStandardMaterial({
      color: '#d9d8cb',
      roughness: 0.85,
      transparent: opacity < 1,
      opacity,
      depthWrite: opacity === 1,
    });
    if (light)
      value.onBeforeCompile = (shader) => {
        shader.uniforms.cityNight = light.night;
        shader.vertexShader =
          'varying vec3 cityPosition;\nvarying vec3 cityNormal;\n' + shader.vertexShader;
        shader.vertexShader = shader.vertexShader.replace(
          '#include <worldpos_vertex>',
          '#include <worldpos_vertex>\n cityPosition=(modelMatrix*vec4(transformed,1.0)).xyz; cityNormal=normalize(mat3(modelMatrix)*objectNormal);'
        );
        shader.fragmentShader =
          'uniform float cityNight;\nvarying vec3 cityPosition;\nvarying vec3 cityNormal;\n' +
          shader.fragmentShader;
        shader.fragmentShader = shader.fragmentShader.replace(
          '#include <emissivemap_fragment>',
          `#include <emissivemap_fragment>
      float wall=1.0-smoothstep(.15,.65,abs(cityNormal.y));
      vec2 facade=vec2(abs(cityNormal.x)>.7?cityPosition.z:cityPosition.x,cityPosition.y)/vec2(2.8,3.3);
      vec2 cell=fract(facade);float seed=fract(sin(dot(floor(facade),vec2(12.9898,78.233)))*43758.5453);
      float window=step(.22,cell.x)*step(cell.x,.72)*step(.22,cell.y)*step(cell.y,.74)*step(.32,seed);
      float resolved=1.0-smoothstep(.35,1.5,max(fwidth(facade.x),fwidth(facade.y)));
      vec3 windowColor=mix(vec3(1.0,.45,.13),vec3(.5,.73,1.0),step(.82,seed));
      totalEmissiveRadiance+=windowColor*cityNight*wall*mix(.03,window*.9,resolved);`
        );
      };
    value.customProgramCacheKey = () => 'urban-windows-v1';
    return value;
  }, [light, opacity]);
  useEffect(() => () => material.dispose(), [material]);
  return <primitive object={material} attach="material" />;
}
