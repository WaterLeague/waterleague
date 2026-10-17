import { useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { Cell, Placement } from '../../game/entity/game';
import { labelLeaderEnd, positionSceneLabels, type SceneLabel } from '../service/sceneLabelService';

function useLabelTexture(text: string, selected: boolean) {
  const width = Math.max(36, Math.min(220, text.length * 7 + 14)),
    height = 26;
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
    context.roundRect(0.5, 0.5, width - 1, height - 1, 4);
    context.fill();
    context.stroke();
    context.font = '600 12px system-ui';
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillStyle = selected ? '#fff' : '#48623d';
    context.fillText(text, width / 2, height / 2, width - 6);
    const map = new THREE.CanvasTexture(canvas);
    map.colorSpace = THREE.SRGBColorSpace;
    return map;
  }, [text, width, selected]);
  useEffect(() => () => texture.dispose(), [texture]);
  return { texture, width, height };
}

export function LabelMarker({
  text,
  position,
  selected = false,
}: {
  text: string;
  position: [number, number, number];
  selected?: boolean;
}) {
  const ref = useRef<THREE.Sprite>(null);
  const { texture, width, height } = useLabelTexture(text, selected);
  useFrame(({ camera }) => {
    ref.current?.scale.set(width / camera.zoom, height / camera.zoom, 1);
  });
  return (
    <sprite ref={ref} position={position} renderOrder={100}>
      <spriteMaterial map={texture} depthTest={false} depthWrite={false} toneMapped={false} />
    </sprite>
  );
}

interface MarkerBinding {
  sprite: THREE.Sprite;
  line: THREE.Line;
  dot: THREE.Points;
  anchor: THREE.Vector3;
  width: number;
  height: number;
  priority: number;
}
type Bindings = { current: Map<string, MarkerBinding> };
const ignoreRaycast = () => {};
function visibleSpriteRaycast(
  this: THREE.Sprite,
  raycaster: THREE.Raycaster,
  hits: THREE.Intersection[]
) {
  if (this.visible) THREE.Sprite.prototype.raycast.call(this, raycaster, hits);
}

function CellMarker({
  cell,
  selected,
  placement,
  preview,
  bindings,
  onSelect,
}: {
  cell: Cell;
  selected: boolean;
  placement?: Placement;
  preview?: Placement;
  bindings: Bindings;
  onSelect: () => void;
}) {
  const sprite = useRef<THREE.Sprite>(null),
    line = useRef<THREE.LineSegments>(null),
    dot = useRef<THREE.Points>(null);
  const text = (preview ? '··· ' : placement ? '✓ ' : '') + cell.id;
  const { texture, width, height } = useLabelTexture(text, selected);
  const anchor = useMemo(
    () => new THREE.Vector3(cell.center[0], cell.heightM + 0.7, -cell.center[1]),
    [cell]
  );
  const lineGeometry = useMemo(
    () =>
      new THREE.BufferGeometry().setAttribute(
        'position',
        new THREE.Float32BufferAttribute(new Float32Array(6), 3)
      ),
    []
  );
  const dotGeometry = useMemo(() => new THREE.BufferGeometry().setFromPoints([anchor]), [anchor]);
  useEffect(
    () => () => {
      lineGeometry.dispose();
      dotGeometry.dispose();
    },
    [lineGeometry, dotGeometry]
  );
  useLayoutEffect(() => {
    if (!sprite.current || !line.current || !dot.current) return;
    const registry = bindings.current;
    registry.set(cell.id, {
      sprite: sprite.current,
      line: line.current,
      dot: dot.current,
      anchor,
      width,
      height,
      priority: selected ? 3 : preview ? 2 : placement ? 1 : 0,
    });
    return () => {
      registry.delete(cell.id);
    };
  }, [cell.id, selected, preview, placement, bindings, anchor, width, height]);
  return (
    <group>
      <lineSegments
        ref={line}
        geometry={lineGeometry}
        renderOrder={99}
        frustumCulled={false}
        raycast={ignoreRaycast}
      >
        <lineBasicMaterial
          color={selected ? '#254f3a' : '#637d63'}
          transparent
          opacity={selected ? 1 : 0.7}
          depthTest={false}
          depthWrite={false}
          toneMapped={false}
        />
      </lineSegments>
      <points
        ref={dot}
        geometry={dotGeometry}
        renderOrder={100}
        frustumCulled={false}
        raycast={ignoreRaycast}
      >
        <pointsMaterial
          color={selected ? '#254f3a' : '#637d63'}
          size={4}
          sizeAttenuation={false}
          depthTest={false}
          depthWrite={false}
          toneMapped={false}
        />
      </points>
      <sprite
        ref={sprite}
        renderOrder={selected ? 102 : 101}
        frustumCulled={false}
        raycast={visibleSpriteRaycast}
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
        <spriteMaterial map={texture} depthTest={false} depthWrite={false} toneMapped={false} />
      </sprite>
    </group>
  );
}

export function CellLabels({
  cells,
  placements,
  preview,
  selectedCell,
  onSelect,
}: {
  cells: Cell[];
  placements: Placement[];
  preview?: Placement;
  selectedCell?: string | null;
  onSelect?: (id: string) => void;
}) {
  const bindings = useRef(new Map<string, MarkerBinding>());
  const projected = useMemo(() => new THREE.Vector3(), []);
  const endpoint = useMemo(() => new THREE.Vector3(), []);
  // 화면에서만 표식을 이동하며 실제 구역 중심·시설 입력은 보존한다.
  useFrame(({ camera, size }) => {
    camera.updateMatrixWorld();
    const labels: SceneLabel[] = [];
    const depths = new Map<string, number>();
    for (const [id, marker] of bindings.current) {
      marker.sprite.visible = marker.line.visible = marker.dot.visible = false;
      projected.copy(marker.anchor).project(camera);
      if (Math.abs(projected.x) > 1 || Math.abs(projected.y) > 1 || Math.abs(projected.z) > 1)
        continue;
      labels.push({
        id,
        x: ((projected.x + 1) * size.width) / 2,
        y: ((1 - projected.y) * size.height) / 2,
        width: marker.width,
        height: marker.height,
        priority: marker.priority,
      });
      depths.set(id, projected.z);
    }
    for (const label of positionSceneLabels(labels, {
      left: 12,
      top: 58,
      right: size.width - 60,
      bottom: size.height - 70,
    })) {
      const marker = bindings.current.get(label.id)!;
      const depth = depths.get(label.id)!;
      marker.sprite.position
        .set((label.x / size.width) * 2 - 1, 1 - (label.y / size.height) * 2, depth)
        .unproject(camera);
      const unitsX = 2 / (camera.projectionMatrix.elements[0] * size.width);
      const unitsY = 2 / (camera.projectionMatrix.elements[5] * size.height);
      marker.sprite.scale.set(label.width * unitsX, label.height * unitsY, 1);
      const original = labels.find((item) => item.id === label.id)!;
      const end = labelLeaderEnd(original, label);
      endpoint
        .set((end.x / size.width) * 2 - 1, 1 - (end.y / size.height) * 2, depth)
        .unproject(camera);
      const positions = marker.line.geometry.getAttribute('position');
      positions.setXYZ(0, marker.anchor.x, marker.anchor.y, marker.anchor.z);
      positions.setXYZ(1, endpoint.x, endpoint.y, endpoint.z);
      positions.needsUpdate = true;
      marker.sprite.visible = marker.dot.visible = true;
      marker.line.visible = Math.hypot(end.x - original.x, end.y - original.y) > 1;
    }
  });
  return (
    <group>
      {cells.map((cell) => (
        <CellMarker
          key={cell.id}
          cell={cell}
          selected={selectedCell === cell.id}
          placement={placements.find((placement) => placement.cellId === cell.id)}
          preview={preview?.cellId === cell.id ? preview : undefined}
          bindings={bindings}
          onSelect={() => onSelect?.(cell.id)}
        />
      ))}
    </group>
  );
}
