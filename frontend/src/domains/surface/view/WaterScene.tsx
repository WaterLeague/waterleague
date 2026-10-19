import { createContext, useCallback, useContext, useEffect, useMemo, useRef } from 'react';
import type { ReactNode } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import {
  DepthTexture,
  LinearFilter,
  Matrix4,
  Object3D,
  UnsignedIntType,
  Vector2,
  Vector4,
  WebGLRenderTarget,
} from 'three';

function createSceneCapture() {
  const target = new WebGLRenderTarget(1, 1, {
    minFilter: LinearFilter,
    magFilter: LinearFilter,
    depthTexture: new DepthTexture(1, 1, UnsignedIntType),
    stencilBuffer: false,
  });
  return {
    target,
    objects: new Set<Object3D>(),
    uniforms: {
      waterSceneColor: { value: target.texture },
      waterSceneDepth: { value: target.depthTexture },
      waterProjectionInverse: { value: new Matrix4() },
      waterViewInverse: { value: new Matrix4() },
      waterResolution: { value: new Vector2(1, 1) },
      waterCaptureReady: { value: 0 },
      waterTime: { value: 0 },
    },
  };
}
const WaterContext = createContext<ReturnType<typeof createSceneCapture> | null>(null);
export function useWaterCapture() {
  return useContext(WaterContext);
}
export function useWaterObject() {
  const capture = useWaterCapture();
  const previous = useRef<Object3D | null>(null);
  return useCallback(
    (object: Object3D | null) => {
      if (previous.current) capture?.objects.delete(previous.current);
      if (object) capture?.objects.add(object);
      previous.current = object;
    },
    [capture]
  );
}
export function WaterScene({ animate, children }: { animate: boolean; children: ReactNode }) {
  const { gl, scene, camera, size, invalidate } = useThree();
  const capture = useMemo(createSceneCapture, []);
  const saved = useMemo(() => ({ viewport: new Vector4(), scissor: new Vector4() }), []);
  useEffect(() => () => capture.target.dispose(), [capture]);
  useEffect(() => {
    const scale = Math.min(1, 1024 / Math.max(size.width, size.height));
    capture.target.setSize(
      Math.max(1, Math.round(size.width * scale)),
      Math.max(1, Math.round(size.height * scale))
    );
    gl.getDrawingBufferSize(capture.uniforms.waterResolution.value);
    invalidate();
  }, [capture, gl, size, invalidate]);
  useEffect(() => {
    if (!animate) return;
    // 수면마다 별도 타이머를 만들지 않고 숨긴 탭에서는 갱신을 멈춘다.
    const timer = window.setInterval(() => {
      if (!document.hidden) invalidate();
    }, 1000 / 30);
    return () => window.clearInterval(timer);
  }, [animate, invalidate]);
  useFrame((_, delta) => {
    if (animate && !document.hidden) capture.uniforms.waterTime.value += Math.min(delta, 0.1);
    capture.uniforms.waterCaptureReady.value = 0;
    if (!capture.objects.size || camera.position.y > 16000) return;
    camera.updateMatrixWorld();
    capture.uniforms.waterProjectionInverse.value.copy(camera.projectionMatrixInverse);
    capture.uniforms.waterViewInverse.value.copy(camera.matrixWorld);
    gl.getDrawingBufferSize(capture.uniforms.waterResolution.value);
    const target = gl.getRenderTarget();
    const cubeFace = gl.getActiveCubeFace();
    const mipLevel = gl.getActiveMipmapLevel();
    const xr = gl.xr.enabled;
    const shadows = gl.shadowMap.autoUpdate;
    const scissorTest = gl.getScissorTest();
    gl.getViewport(saved.viewport);
    gl.getScissor(saved.scissor);
    const hidden = [...capture.objects].filter((object) => object.visible);
    try {
      // 모든 수면을 제외한 같은 장면을 한 번만 그려 반사·굴절의 자기 참조를 막는다.
      hidden.forEach((object) => (object.visible = false));
      gl.xr.enabled = false;
      gl.shadowMap.autoUpdate = false;
      gl.setRenderTarget(capture.target);
      gl.setScissorTest(false);
      gl.clear();
      gl.render(scene, camera);
      capture.uniforms.waterCaptureReady.value = 1;
    } finally {
      hidden.forEach((object) => (object.visible = true));
      gl.xr.enabled = xr;
      gl.shadowMap.autoUpdate = shadows;
      gl.setRenderTarget(target, cubeFace, mipLevel);
      gl.setViewport(saved.viewport);
      gl.setScissor(saved.scissor);
      gl.setScissorTest(scissorTest);
    }
  }, -0.1);
  return <WaterContext.Provider value={capture}>{children}</WaterContext.Provider>;
}
