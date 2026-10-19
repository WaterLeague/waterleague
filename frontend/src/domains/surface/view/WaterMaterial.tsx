import { memo, useEffect, useMemo } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { DoubleSide, ShaderMaterial, Vector2 } from 'three';
import { calmWater, type WaterWeather } from '../service/waterAppearanceService';

const vertexShader = `
  attribute vec2 flow;
  varying vec3 vWaterColor;
  varying vec3 vWorld;
  varying vec2 vFlow;
  void main() {
    vWaterColor = color;
    vFlow = flow;
    vec4 world = modelMatrix * vec4(position, 1.0);
    vWorld = world.xyz;
    gl_Position = projectionMatrix * viewMatrix * world;
  }
`;
const fragmentShader = `
  uniform float time;
  uniform vec2 wind;
  uniform float rain;
  uniform float natural;
  uniform float gust;
  varying vec3 vWaterColor;
  varying vec3 vWorld;
  varying vec2 vFlow;
  void main() {
    vec2 p = vWorld.xz;
    vec2 drift = vFlow * time;
    vec2 breeze = wind * time * 0.08;
    vec2 q = p - drift - breeze;
    float wavelength = mix(2.8, 26.0, natural);
    float phase = (q.x + q.y * 0.47) / wavelength;
    float ripple = sin(phase * 6.283) * 0.5 + sin((q.y - q.x * 0.31) / wavelength * 9.0 + time * 0.6) * 0.3;
    float drops = sin(length(fract(p / 7.0) - 0.5) * 42.0 - time * 7.0) * clamp(rain * 2.0, 0.0, 0.45);
    float resolved = 1.0 - smoothstep(0.5, 2.8, length(fwidth(p / wavelength)));
    float roughness = 0.10 + sqrt(min(gust, 20.0)) * 0.035;
    vec3 normal = normalize(vec3((ripple + drops) * resolved * roughness, 1.0, cos(phase * 6.283) * resolved * roughness));
    vec3 eye = normalize(cameraPosition - vWorld);
    float fresnel = pow(1.0 - max(dot(eye, normal), 0.0), 3.0);
    float glint = pow(max(dot(reflect(-normalize(vec3(-0.4, 0.8, 0.35)), normal), eye), 0.0), 64.0);
    vec3 base = vWaterColor * (1.0 + ripple * resolved * 0.09);
    vec3 result = mix(base, vec3(0.68, 0.83, 0.87), fresnel * mix(0.10, 0.35, natural));
    result += glint * 0.35 + drops * resolved * 0.035;
    float sheen = pow(0.5 + 0.5 * sin(phase * 6.283), 12.0) * resolved;
    result += vec3(0.035, 0.055, 0.065) * sheen;
    gl_FragColor = vec4(result, mix(0.76, 0.94, natural));
    #include <colorspace_fragment>
  }
`;
export const WaterMaterial = memo(function WaterMaterial({
  animate,
  natural = false,
  weather = calmWater,
}: {
  animate: boolean;
  natural?: boolean;
  weather?: WaterWeather;
}) {
  const invalidate = useThree((s) => s.invalidate);
  const material = useMemo(
    () =>
      new ShaderMaterial({
        vertexShader,
        fragmentShader,
        vertexColors: true,
        transparent: true,
        depthWrite: false,
        depthTest: natural,
        side: DoubleSide,
        toneMapped: false,
        uniforms: {
          time: { value: 0 },
          wind: { value: new Vector2() },
          rain: { value: 0 },
          gust: { value: 0 },
          natural: { value: natural ? 1 : 0 },
        },
      }),
    [natural]
  );
  useEffect(() => () => material.dispose(), [material]);
  useEffect(() => {
    material.uniforms.wind.value.set(...weather.wind);
    material.uniforms.rain.value = weather.rain;
    material.uniforms.gust.value = weather.windSpeed ?? Math.hypot(...weather.wind);
    invalidate();
  }, [material, weather, invalidate]);
  useFrame((_, delta) => {
    if (animate) material.uniforms.time.value += Math.min(delta, 0.1);
  });
  return <primitive object={material} attach="material" />;
});

export function WaterAnimation({ animate }: { animate: boolean }) {
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    if (!animate) return;
    // 모든 수면은 한 타이머로 갱신하고 숨긴 탭과 정지 상태에서는 렌더를 깨우지 않는다.
    const timer = window.setInterval(() => {
      if (!document.hidden) invalidate();
    }, 1000 / 30);
    return () => window.clearInterval(timer);
  }, [animate, invalidate]);
  return null;
}
