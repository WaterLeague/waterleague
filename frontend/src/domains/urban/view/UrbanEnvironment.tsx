import { createContext, useContext, useEffect, useMemo, useRef } from 'react';
import type { ReactNode } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import {
  BackSide,
  Color,
  DirectionalLight,
  HemisphereLight,
  Mesh,
  Object3D,
  ShaderMaterial,
  Vector3,
} from 'three';
import type { UrbanTime } from '../entity/urban';
import { daylight, solarPosition } from '../service/solarService';
import { urbanTime } from '../service/urbanTimeService';
const LightingContext = createContext<ReturnType<typeof uniforms> | null>(null);
function uniforms() {
  return {
    night: { value: 0 },
    day: { value: 1 },
    sunDirection: { value: new Vector3(0, 1, 0) },
    solarElevation: { value: 45 },
  };
}
export function useUrbanLighting() {
  return useContext(LightingContext);
}
export function UrbanEnvironment({ clock, children }: { clock: UrbanTime; children: ReactNode }) {
  const values = useMemo(uniforms, []);
  return (
    <LightingContext.Provider value={values}>
      <Lighting clock={clock} />
      {children}
    </LightingContext.Provider>
  );
}
function Lighting({ clock }: { clock: UrbanTime }) {
  const values = useUrbanLighting()!;
  const sun = useRef<DirectionalLight>(null),
    ambient = useRef<HemisphereLight>(null),
    sky = useRef<Mesh>(null),
    disk = useRef<Mesh>(null);
  const target = useMemo(() => new Object3D(), []);
  const { invalidate, scene } = useThree();
  const material = useMemo(
    () =>
      new ShaderMaterial({
        side: BackSide,
        depthWrite: false,
        uniforms: values,
        vertexShader: `varying vec3 direction; void main(){direction=position; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
        fragmentShader: `uniform float day; uniform float solarElevation; uniform vec3 sunDirection; varying vec3 direction;
    void main(){vec3 ray=normalize(direction);float horizon=pow(1.0-max(0.0,ray.y),3.0);
    vec3 top=mix(vec3(.012,.025,.065),vec3(.19,.43,.66),day);
    vec3 low=mix(vec3(.045,.067,.105),vec3(.64,.77,.82),day);
    float dusk=(1.0-smoothstep(0.0,18.0,abs(solarElevation)))*smoothstep(-12.0,-1.0,solarElevation);
    low=mix(low,vec3(.84,.35,.15),dusk*pow(max(dot(ray,sunDirection),0.0),2.0)*.7);
    vec3 result=mix(top,low,horizon);
    float halo=pow(max(dot(ray,sunDirection),0.0),500.0)*smoothstep(-3.0,1.0,solarElevation);
    gl_FragColor=vec4(result+vec3(1.0,.67,.26)*halo*.7,1.0);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
    }`,
      }),
    [values]
  );
  useEffect(() => () => material.dispose(), [material]);
  useEffect(() => {
    scene.add(target);
    return () => {
      scene.remove(target);
    };
  }, [scene, target]);
  useEffect(() => {
    const listeners = clock.current.listeners;
    listeners?.add(invalidate);
    const timer = setInterval(() => {
      if (!document.hidden && !clock.current.historical) invalidate();
    }, 1000);
    return () => {
      clearInterval(timer);
      listeners?.delete(invalidate);
    };
  }, [clock, invalidate]);
  const warm = useMemo(() => new Color('#ffd2a0'), []),
    white = useMemo(() => new Color('#fff7e6'), []);
  useFrame(({ camera, controls }) => {
    const at = urbanTime(clock);
    if (at == null) return;
    const solar = solarPosition(at),
      day = daylight(solar.elevation);
    values.day.value = day;
    values.night.value = 1 - day;
    values.solarElevation.value = solar.elevation;
    values.sunDirection.value.set(...solar.direction);
    if (sky.current) sky.current.position.copy(camera.position);
    if (disk.current) {
      disk.current.position
        .copy(camera.position)
        .addScaledVector(values.sunDirection.value, 115000);
      disk.current.visible = solar.elevation > -0.83;
    }
    if (ambient.current) {
      ambient.current.intensity = 0.55 + day * 0.85;
      ambient.current.color.set(day > 0.5 ? '#cce7ff' : '#9aacc6');
      ambient.current.groundColor.set(day > 0.5 ? '#a19a83' : '#4c5d76');
    }
    if (sun.current) {
      target.position.set(camera.position.x, 0, camera.position.z);
      if (controls && 'target' in controls && controls.target instanceof Vector3)
        target.position.copy(controls.target);
      target.updateMatrixWorld();
      sun.current.target = target;
      sun.current.position.copy(target.position).addScaledVector(values.sunDirection.value, 30000);
      sun.current.intensity = solar.elevation > 0 ? 2.5 * Math.min(1, solar.elevation / 12) : 0;
      sun.current.color.copy(warm).lerp(white, Math.min(1, Math.max(0, solar.elevation / 25)));
      sun.current.castShadow = camera.position.y < 7000 && solar.elevation > 0;
      const extent = Math.max(
        250,
        Math.min(3500, Math.ceil(camera.position.distanceTo(target.position) / 100) * 100)
      );
      const shadowCamera = sun.current.shadow.camera;
      if (shadowCamera.right !== extent) {
        shadowCamera.left = shadowCamera.bottom = -extent;
        shadowCamera.right = shadowCamera.top = extent;
        shadowCamera.updateProjectionMatrix();
      }
    }
  }, -0.3);
  return (
    <>
      <hemisphereLight ref={ambient} args={['#cce7ff', '#a19a83', 1.2]} />
      <directionalLight
        ref={sun}
        shadow-mapSize={[1024, 1024]}
        shadow-camera-left={-3500}
        shadow-camera-right={3500}
        shadow-camera-top={3500}
        shadow-camera-bottom={-3500}
        shadow-camera-near={1}
        shadow-camera-far={65000}
        shadow-bias={-0.0001}
        shadow-normalBias={0.6}
      />
      <mesh ref={sky} renderOrder={-100} raycast={() => {}}>
        <sphereGeometry args={[120000, 24, 16]} />
        <primitive object={material} attach="material" />
      </mesh>
      <mesh ref={disk} raycast={() => {}}>
        <sphereGeometry args={[535, 20, 12]} />
        <meshBasicMaterial color="#fff0b2" toneMapped={false} />
      </mesh>
    </>
  );
}
