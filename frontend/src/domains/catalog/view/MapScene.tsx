import { useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { Canvas, useThree, useFrame } from '@react-three/fiber';
import { OrbitControls, Edges } from '@react-three/drei';
import * as THREE from 'three';
import type { Building, CandidateMap, Transport } from '../entity/catalog';
import { buildingPolygons, polygonShapes } from '../service/mapGeometryService';
import { buildingLabel } from '../service/catalogService';
import type { Cell, Placement } from '../../game/entity/game';
import { FacilityMesh } from './FacilityMesh';
import { watchContextLoss } from '../service/sceneLifecycleService';
import { useReducedMotion } from '../controller/useReducedMotion';

function SceneLifecycle({ onUnavailable }: { onUnavailable?: () => void }) {
  const { gl } = useThree();
  useEffect(() => {
    const stop = watchContextLoss(gl.domElement, () => onUnavailable?.());
    if (gl.getContext().isContextLost()) onUnavailable?.();
    return () => {
      stop();
      document.body.style.cursor = 'auto';
    };
  }, [gl, onUnavailable]);
  return null;
}

function LabelMarker({
  text,
  position,
  selected = false,
  onSelect,
}: {
  text: string;
  position: [number, number, number];
  selected?: boolean;
  onSelect?: () => void;
}) {
  const ref = useRef<THREE.Sprite>(null);
  const width = Math.max(28, Math.min(220, text.length * 7 + 14)),
    height = 23;
  const texture = useMemo(() => {
    const canvas = document.createElement('canvas');
    canvas.width = width * 4;
    canvas.height = height * 4;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('지도 표식 렌더링 불가');
    context.scale(4, 4);
    context.fillStyle = selected ? '#284e3c' : '#fafdf4';
    context.strokeStyle = selected ? '#284e3c' : '#aabb9b';
    context.lineWidth = 1;
    context.beginPath();
    context.roundRect(0.5, 0.5, width - 1, height - 1, 3);
    context.fill();
    context.stroke();
    context.font = '600 11px system-ui';
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillStyle = selected ? '#fff' : '#48623d';
    context.fillText(text, width / 2, height / 2, width - 6);
    const map = new THREE.CanvasTexture(canvas);
    map.colorSpace = THREE.SRGBColorSpace;
    return map;
  }, [text, width, selected]);
  useEffect(() => () => texture.dispose(), [texture]);
  // 별도 DOM 루트 없이 표식을 그려 지도 전환 시 React 루트 정리 충돌 방지.
  useFrame(({ camera }) => {
    if (ref.current) ref.current.scale.set(width / camera.zoom, height / camera.zoom, 1);
  });
  return (
    <sprite
      ref={ref}
      position={position}
      renderOrder={100}
      onClick={(e) => {
        e.stopPropagation();
        onSelect?.();
      }}
    >
      <spriteMaterial map={texture} depthTest={false} depthWrite={false} toneMapped={false} />
    </sprite>
  );
}

function FitDistrict({ map }: { map: CandidateMap }) {
  const { camera, size } = useThree();
  useLayoutEffect(() => {
    if (!(camera instanceof THREE.OrthographicCamera)) return;
    camera.lookAt(0, 0, 0);
    camera.updateMatrixWorld();
    let x = 0,
      y = 0;
    for (const building of map.buildings)
      for (const [east, north] of buildingPolygons(building).flatMap((polygon) => polygon[0]))
        for (const height of [0, building.heightM]) {
          const point = new THREE.Vector3(east, height, -north).applyMatrix4(
            camera.matrixWorldInverse
          );
          x = Math.max(x, Math.abs(point.x));
          y = Math.max(y, Math.abs(point.y));
        }
    // 상단 안내와 하단 도구 공간을 제외해 작은 화면에서도 구역 전체를 표시한다.
    camera.zoom = Math.min(size.width / (2 * x + 60), (size.height - 110) / (2 * y + 50));
    camera.updateProjectionMatrix();
  }, [camera, size.width, size.height, map]);
  return null;
}

function BuildingMesh({
  building,
  selected,
  onSelect,
}: {
  building: Building;
  selected: boolean;
  onSelect: () => void;
}) {
  const geometry = useMemo(() => {
    return new THREE.ExtrudeGeometry(polygonShapes(buildingPolygons(building)), {
      depth: building.heightM,
      bevelEnabled: false,
    });
  }, [building]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <group>
      <mesh
        geometry={geometry}
        rotation={[-Math.PI / 2, 0, 0]}
        castShadow
        receiveShadow
        onClick={(event) => {
          event.stopPropagation();
          onSelect();
        }}
        onPointerOver={(event) => {
          event.stopPropagation();
          document.body.style.cursor = 'pointer';
        }}
        onPointerOut={() => {
          document.body.style.cursor = 'auto';
        }}
      >
        <meshStandardMaterial color={selected ? '#719d82' : '#e5e6db'} roughness={0.85} />
        <Edges threshold={25} color={selected ? '#255d43' : '#b7c1b2'} linewidth={0.55} />
      </mesh>
      {selected && (
        <LabelMarker
          text={buildingLabel(building)}
          position={[building.center[0], building.heightM + 7, -building.center[1]]}
          selected
        />
      )}
    </group>
  );
}

function Roads({ map }: { map: CandidateMap }) {
  const geometry = useMemo(() => {
    const points: number[] = [];
    for (const road of map.roads) {
      const width = ['primary', 'secondary'].includes(road.highway)
        ? 6
        : road.highway === 'footway'
          ? 1.7
          : 3.5;
      for (let i = 0; i < road.coordinates.length - 1; i++) {
        const a = road.coordinates[i],
          b = road.coordinates[i + 1];
        if (
          [a, b].some(
            (p) =>
              Math.abs(p[0]) > map.snapshot.widthM / 2 + 8 ||
              Math.abs(p[1]) > map.snapshot.depthM / 2 + 8
          )
        )
          continue;
        const dx = b[0] - a[0],
          dy = b[1] - a[1],
          length = Math.hypot(dx, dy);
        if (!length) continue;
        const nx = (-dy / length) * width,
          ny = (dx / length) * width;
        const vertices = [
          [a[0] + nx, 0.035, -a[1] - ny],
          [b[0] + nx, 0.035, -b[1] - ny],
          [b[0] - nx, 0.035, -b[1] + ny],
          [a[0] - nx, 0.035, -a[1] + ny],
        ];
        for (const j of [0, 2, 1, 0, 3, 2]) points.push(...vertices[j]);
      }
    }
    const result = new THREE.BufferGeometry();
    result.setAttribute('position', new THREE.Float32BufferAttribute(points, 3));
    result.computeVertexNormals();
    return result;
  }, [map]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <mesh geometry={geometry} receiveShadow>
      <meshStandardMaterial color="#c1c9bc" roughness={1} side={THREE.DoubleSide} />
    </mesh>
  );
}

function TransportMesh({ surface }: { surface: Transport }) {
  const geometry = useMemo(
    () => new THREE.ShapeGeometry(polygonShapes(surface.polygons)),
    [surface]
  );
  useEffect(() => () => geometry.dispose(), [geometry]);
  const colors = { roads: '#bcc5bb', railways: '#a8b1ad', bridges: '#bdc4bb' };
  const levels = { roads: 0.035, railways: 0.045, bridges: 0.055 };
  return (
    <mesh
      geometry={geometry}
      rotation={[-Math.PI / 2, 0, 0]}
      position={[0, levels[surface.transportType], 0]}
      receiveShadow
    >
      <meshStandardMaterial
        color={colors[surface.transportType]}
        roughness={1}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}

function Surface({
  cell,
  placement,
  preview,
  selected,
  onSelect,
}: {
  cell: Cell;
  placement?: Placement;
  preview?: Placement;
  selected: boolean;
  onSelect: () => void;
}) {
  const geometry = useMemo(() => {
    const shape = new THREE.Shape();
    cell.coordinates.forEach(([x, y], i) => (i ? shape.lineTo(x, y) : shape.moveTo(x, y)));
    return new THREE.ShapeGeometry(shape);
  }, [cell]);
  const displayed = preview ?? placement;
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <group>
      <mesh
        geometry={geometry}
        rotation={[-Math.PI / 2, 0, 0]}
        position={[0, cell.heightM + 0.2, 0]}
        onClick={(e) => {
          e.stopPropagation();
          onSelect();
        }}
      >
        <meshStandardMaterial
          color={selected ? '#467c63' : '#95b89c'}
          transparent
          opacity={selected ? 0.55 : 0.22}
          roughness={0.9}
          side={THREE.DoubleSide}
        />
        <Edges color={selected ? '#1d553c' : '#779982'} linewidth={selected ? 1.5 : 0.8} />
      </mesh>
      {displayed && (
        <FacilityMesh cell={cell} placement={displayed} preview={!!preview} onSelect={onSelect} />
      )}
      <LabelMarker
        text={(preview ? '··· ' : placement ? '✓ ' : '') + cell.id}
        position={[cell.center[0], cell.heightM + 4, -cell.center[1]]}
        selected={selected}
        onSelect={onSelect}
      />
    </group>
  );
}
export default function MapScene({
  map,
  selected,
  onSelect,
  topView,
  reset,
  cells = [],
  placements = [],
  preview,
  selectedCell,
  onCellSelect,
  onUnavailable,
}: {
  map: CandidateMap;
  selected: string | null;
  onSelect: (id: string | null) => void;
  topView: boolean;
  reset: number;
  cells?: Cell[];
  placements?: Placement[];
  preview?: Placement;
  selectedCell?: string | null;
  onCellSelect?: (id: string) => void;
  onUnavailable?: () => void;
}) {
  const reducedMotion = useReducedMotion();
  return (
    <Canvas
      key={`${map.snapshot.id}-${topView}-${reset}`}
      shadows="percentage"
      dpr={[1, 1.7]}
      frameloop="demand"
      orthographic
      camera={{
        position: topView ? [0, 460, 0.1] : [310, 320, 380],
        zoom: 2.0,
        near: 0.1,
        far: 1500,
      }}
      onPointerMissed={cells.length ? undefined : () => onSelect(null)}
      gl={{ antialias: true, powerPreference: 'high-performance' }}
    >
      <SceneLifecycle onUnavailable={onUnavailable} />
      <color attach="background" args={['#e6eae1']} />
      <hemisphereLight args={['#f7f7ec', '#78917f', 2.1]} />
      <directionalLight
        position={[-130, 280, 130]}
        intensity={3.0}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-220}
        shadow-camera-right={220}
        shadow-camera-top={220}
        shadow-camera-bottom={-220}
        shadow-camera-near={1}
        shadow-camera-far={700}
        shadow-bias={-0.0003}
        shadow-normalBias={0.25}
      />
      <mesh position={[0, -3.1, 0]} receiveShadow>
        <boxGeometry args={[map.snapshot.widthM + 26, 6, map.snapshot.depthM + 26]} />
        <meshStandardMaterial color="#d3dccd" roughness={1} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.05, 0]} receiveShadow>
        <planeGeometry args={[map.snapshot.widthM + 24, map.snapshot.depthM + 24]} />
        <meshStandardMaterial color="#e4e7d9" roughness={1} />
      </mesh>
      <Roads map={map} />
      {map.transports.map((surface) => (
        <TransportMesh key={surface.id} surface={surface} />
      ))}
      <FitDistrict map={map} />
      {map.buildings.map((building) => (
        <BuildingMesh
          key={building.id}
          building={building}
          selected={selected === building.id}
          onSelect={() => onSelect(building.id)}
        />
      ))}
      {cells.map((cell) => (
        <Surface
          key={cell.id}
          cell={cell}
          placement={placements.find((p) => p.cellId === cell.id)}
          preview={preview?.cellId === cell.id ? preview : undefined}
          selected={selectedCell === cell.id}
          onSelect={() => onCellSelect?.(cell.id)}
        />
      ))}
      <OrbitControls
        makeDefault
        enableDamping={!reducedMotion}
        dampingFactor={0.12}
        minZoom={0.3}
        maxZoom={6}
        minPolarAngle={0.05}
        maxPolarAngle={Math.PI / 2.4}
        target={[0, 0, 0]}
        enableRotate={!topView}
      />
    </Canvas>
  );
}
