import { memo, useEffect, useMemo } from 'react';
import { useThree } from '@react-three/fiber';
import { DoubleSide, ShaderMaterial, Vector2 } from 'three';
import { calmWater, type WaterWeather } from '../service/waterAppearanceService';
import { useWaterCapture } from './WaterScene';
import { useUrbanLighting } from '../../urban/view/UrbanEnvironment';

const waves = `
  uniform float waterTime;
  uniform vec2 wind;
  uniform float gust;
  uniform float rain;
  uniform float natural;
  uniform float record;
  uniform float daylightFactor;
  uniform vec3 solarDirection;
  vec2 windAxis() { return length(wind) > 0.001 ? normalize(wind) : vec2(1.0, 0.0); }
  float waveHeight(vec2 p, float depth) {
    vec2 axis = windAxis();
    float amplitude = min(gust * 0.014, 0.18) * mix(min(depth * 0.08, 0.12), 1.0, natural);
    float phase = dot(p, axis) * 0.065 - waterTime * sqrt(gust) * 0.42 * step(0.001, length(wind));
    return amplitude * (sin(phase) * 0.65 + sin(dot(p, vec2(-axis.y, axis.x)) * 0.11 + phase * 0.6) * 0.35);
  }
`;
const vertexShader = `
  ${waves}
  attribute vec2 flow;
  attribute float waterDepth;
  attribute float waterFace;
  varying vec3 vWaterColor;
  varying vec3 vWorld;
  varying vec3 vNormal;
  varying vec2 vFlow;
  varying float vDepth;
  varying float vFace;
  void main() {
    vWaterColor = color;
    vFlow = flow;
    vDepth = waterDepth;
    vFace = waterFace;
    vec4 world = modelMatrix * vec4(position, 1.0);
    if (waterFace > 0.5) world.y += waveHeight(world.xz, waterDepth);
    vWorld = world.xyz;
    vNormal = normalize(mat3(modelMatrix) * normal);
    gl_Position = projectionMatrix * viewMatrix * world;
  }
`;
const fragmentShader = `
  ${waves}
  uniform mat4 projectionMatrix;
  uniform sampler2D waterSceneColor;
  uniform sampler2D waterSceneDepth;
  uniform mat4 waterProjectionInverse;
  uniform mat4 waterViewInverse;
  uniform vec2 waterResolution;
  uniform float waterCaptureReady;
  varying vec3 vWaterColor;
  varying vec3 vWorld;
  varying vec3 vNormal;
  varying vec2 vFlow;
  varying float vDepth;
  varying float vFace;
  vec3 viewAt(vec2 uv) {
    float depth = texture2D(waterSceneDepth, uv).r;
    vec4 point = waterProjectionInverse * vec4(uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
    return point.xyz / point.w;
  }
  vec2 projectView(vec3 point) {
    vec4 clip = projectionMatrix * vec4(point, 1.0);
    return clip.xy / clip.w * 0.5 + 0.5;
  }
  vec4 reflectionAt(vec3 start, vec3 normal) {
    vec3 ray = reflect(normalize(start), normal);
    float stride = clamp(-start.z * 0.0012, 0.4, 6.0);
    vec3 previous = start + normal * 0.06;
    float travelled = stride;
    for (int i = 0; i < 32; i++) {
      vec3 point = start + ray * travelled;
      vec2 uv = projectView(point);
      if (point.z >= -0.1 || any(lessThan(uv, vec2(0.002))) || any(greaterThan(uv, vec2(0.998)))) break;
      vec3 scenePoint = viewAt(uv);
      float gap = scenePoint.z - point.z;
      if (gap >= 0.0 && gap < stride * (1.0 + float(i) * 0.2) + 0.5) {
        vec3 low = previous;
        vec3 high = point;
        for (int j = 0; j < 5; j++) {
          vec3 middle = (low + high) * 0.5;
          if (viewAt(projectView(middle)).z - middle.z > 0.0) high = middle;
          else low = middle;
        }
        uv = projectView((low + high) * 0.5);
        vec3 worldHit = (waterViewInverse * vec4(viewAt(uv), 1.0)).xyz;
        float valid = step(vWorld.y - 0.1, worldHit.y);
        float edge = smoothstep(0.0, 0.08, min(min(uv.x, 1.0 - uv.x), min(uv.y, 1.0 - uv.y)));
        return vec4(texture2D(waterSceneColor, uv).rgb, edge * valid);
      }
      previous = point;
      travelled += stride * (1.0 + float(i) * 0.2);
    }
    return vec4(0.0);
  }
  float ring(vec2 p) {
    vec2 cell = floor(p);
    float seed = fract(sin(dot(cell, vec2(127.1, 311.7))) * 43758.5453);
    vec2 center = vec2(fract(seed * 19.3), fract(seed * 71.7));
    float age = fract(waterTime * 0.8 + seed);
    float radius = length(fract(p) - center);
    return sin((radius - age * 0.8) * 48.0) * exp(-abs(radius - age * 0.8) * 18.0) * (1.0 - age);
  }
  vec2 surfaceSlope(vec2 p, vec2 axis, vec2 across, float wavelength, float phase, float pulse) {
    vec2 q = vec2(dot(p, axis), dot(p, across)) * 6.283185 / wavelength;
    float visible = 1.0 - smoothstep(0.7, 2.4, max(fwidth(q.x), fwidth(q.y)));
    // 풍향이 없어도 제자리 진동을 유지하며 임의의 이류 방향은 만들지 않는다.
    float a = sin(q.x + sin(q.y * 0.73) * 0.85 - phase) * cos(pulse);
    float b = cos(q.y * 0.87 + sin(q.x * 0.61) * 0.8 - phase * 0.71) * sin(pulse * 0.83 + 0.7);
    return (axis * a + across * b * 0.65) * visible;
  }
  void main() {
    if (vFace < -0.5) {
      gl_FragColor = vec4(vWaterColor, 1.0);
    } else {
      vec2 p = vWorld.xz - vFlow * waterTime;
      vec2 axis = windAxis();
      vec2 across = vec2(-axis.y, axis.x);
      float windPhase = waterTime * sqrt(gust) * 0.65 * step(0.001, length(wind));
      float pulse = waterTime * 1.15;
      float resolved = 1.0 - smoothstep(0.35, 2.5, length(fwidth(p * 0.5)));
      float drops = (ring(p * 0.55) + ring(p * 0.55 + vec2(0.0, 1.0))) * min(rain * 0.5, 0.5);
      float rough = min(0.075 + sqrt(gust) * 0.065, 0.26);
      vec2 slope = surfaceSlope(p, axis, across, 2.5, windPhase * 1.8, pulse * 1.3) * 0.55;
      slope += surfaceSlope(p, axis, across, 18.0, windPhase * 1.2, pulse) * 0.65;
      slope += surfaceSlope(p, axis, across, 95.0, windPhase * 0.9, pulse * 0.87) * 0.75;
      slope += surfaceSlope(p, axis, across, 450.0, windPhase * 0.7, pulse * 0.73) * 0.55;
      // 서울 전체 축척의 법선 표현만 보강하며 실제 파고·수심은 늘리지 않는다.
      float overview = smoothstep(12.0, 65.0, length(fwidth(p)));
      slope += surfaceSlope(p, axis, across, 1800.0, windPhase * 0.6, pulse * 0.65) * overview * 0.8;
      slope = slope * rough + vec2(drops) * resolved * 0.04;
      float h = waveHeight(p, vDepth);
      slope += vec2(h - waveHeight(p + vec2(0.2, 0.0), vDepth), h - waveHeight(p + vec2(0.0, 0.2), vDepth)) / 0.2;
      vec3 normal = vFace > 0.5 ? normalize(vec3(slope.x, 1.0, slope.y)) : normalize(vNormal);
      if (!gl_FrontFacing) normal = -normal;
      vec3 eye = normalize(cameraPosition - vWorld);
      float fresnel = 0.02 + 0.98 * pow(1.0 - max(dot(eye, normal), 0.0), 5.0);
      vec3 skyRay = reflect(-eye, normal);
      float skyGradient = smoothstep(-0.2, 0.8, skyRay.y);
      vec3 sky = mix(vec3(0.42, 0.61, 0.69), vec3(0.10, 0.28, 0.40), skyGradient);
      float clouds = smoothstep(0.0, 0.65, sin(skyRay.x * 9.0 + skyRay.z * 4.0) * cos(skyRay.z * 7.0 - skyRay.x * 3.0));
      sky = mix(sky, vec3(0.76, 0.82, 0.83), clouds * 0.45);
      sky = mix(sky, vec3(dot(sky, vec3(0.2126, 0.7152, 0.0722))), min(rain * 0.15, 0.4));
      sky *= mix(0.045, 1.0, daylightFactor);
      vec3 base = vWaterColor * mix(0.12, 1.0, daylightFactor);
      vec3 reflected = sky;
      float sceneReflection = 0.0;
      if (waterCaptureReady > 0.5) {
        vec2 uv = gl_FragCoord.xy / waterResolution;
        vec2 refractedUv = clamp(uv + slope * 0.009, vec2(0.001), vec2(0.999));
        vec3 below = viewAt(refractedUv);
        vec3 belowWorld = (waterViewInverse * vec4(below, 1.0)).xyz;
        if (belowWorld.y > vWorld.y + 0.03) { refractedUv = uv; below = viewAt(uv); }
        vec3 viewPoint = (viewMatrix * vec4(vWorld, 1.0)).xyz;
        float thickness = max(0.0, length(below - viewPoint));
        float transmission = mix(exp(-thickness * mix(1.4, 0.5, natural)) * mix(0.16, 0.38, natural), 0.32, record);
        base = mix(base, texture2D(waterSceneColor, refractedUv).rgb, transmission);
        if (vFace > 0.5 && length(viewPoint) < 12000.0) {
          vec4 hit = reflectionAt(viewPoint, normalize(mat3(viewMatrix) * normal));
          reflected = mix(sky, hit.rgb, hit.a);
          sceneReflection = hit.a;
        }
      }
      float reflectionWeight = mix(0.12, 0.18, natural) + fresnel * mix(0.20, 0.60, natural) + sceneReflection * natural * 0.2;
      vec3 result = mix(base, reflected, reflectionWeight);
      vec3 sun = normalize(solarDirection);
      float glint = pow(max(dot(reflect(-sun, normal), eye), 0.0), mix(160.0, 64.0, min(gust / 15.0, 1.0)));
      float crestLight = clamp(dot(normal, sun), 0.0, 1.0);
      result *= 0.72 + crestLight * 0.4;
      result += glint * 0.55 * daylightFactor + drops * resolved * 0.025 * daylightFactor;
      result *= vFace > 0.5 ? 1.0 : 0.8;
      gl_FragColor = vec4(result, 1.0);
    }
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;
export const WaterMaterial = memo(function WaterMaterial({
  natural = false,
  record = false,
  weather = calmWater,
}: {
  natural?: boolean;
  record?: boolean;
  weather?: WaterWeather;
}) {
  const invalidate = useThree((s) => s.invalidate);
  const capture = useWaterCapture();
  const lighting = useUrbanLighting();
  const material = useMemo(() => {
    if (!capture) return null;
    return new ShaderMaterial({
      vertexShader,
      fragmentShader,
      vertexColors: true,
      depthWrite: true,
      depthTest: true,
      side: DoubleSide,
      uniforms: {
        ...capture.uniforms,
        daylightFactor: lighting?.day ?? { value: 1 },
        solarDirection: lighting?.sunDirection ?? { value: [-0.4, 0.8, 0.35] },
        wind: { value: new Vector2() },
        rain: { value: 0 },
        gust: { value: 0 },
        natural: { value: natural ? 1 : 0 },
        record: { value: record ? 1 : 0 },
      },
    });
  }, [natural, record, capture, lighting]);
  useEffect(() => () => material?.dispose(), [material]);
  useEffect(() => {
    if (!material) return;
    material.uniforms.wind.value.set(...weather.wind);
    material.uniforms.rain.value = weather.rain;
    material.uniforms.gust.value = weather.windSpeed ?? Math.hypot(...weather.wind);
    invalidate();
  }, [material, weather, invalidate]);
  return material ? <primitive object={material} attach="material" /> : null;
});
