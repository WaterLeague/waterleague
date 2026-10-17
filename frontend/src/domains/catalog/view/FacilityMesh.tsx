import { useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import type { Cell, Placement } from '../../game/entity/game';
import type { FacilityFootprint } from '../entity/facilityFootprint';
import { facilityFootprint, plantingMarkers } from '../service/facilityGeometryService';
import { CatalogError } from '../exception/CatalogError';

function Planting({
  footprint,
  roof,
  opacity,
}: {
  footprint: FacilityFootprint;
  roof: boolean;
  opacity: number;
}) {
  const points = useMemo(() => plantingMarkers(footprint), [footprint]);
  const ref = useRef<THREE.InstancedMesh>(null);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    const dummy = new THREE.Object3D();
    points.forEach(([east, north], index) => {
      dummy.position.set(east, roof ? 0.64 : 1.05, -north);
      dummy.rotation.y = index * 2.4;
      dummy.updateMatrix();
      mesh.setMatrixAt(index, dummy.matrix);
      mesh.setColorAt(index, new THREE.Color(index % 3 === 0 ? '#9db66a' : '#557b4a'));
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.computeBoundingSphere();
  }, [points, roof]);
  if (!points.length) return null;
  return (
    <instancedMesh ref={ref} args={[undefined, undefined, points.length]} castShadow receiveShadow>
      <coneGeometry args={[0.65, roof ? 0.55 : 1.35, 5]} />
      <meshStandardMaterial
        roughness={1}
        transparent={opacity < 1}
        opacity={opacity}
        depthWrite={opacity === 1}
      />
    </instancedMesh>
  );
}

export function FacilityMesh({
  cell,
  placement,
  preview,
  onSelect,
  opacity = 1,
}: {
  cell: Pick<Cell, 'coordinates' | 'areaM2' | 'heightM'>;
  placement: Placement;
  preview: boolean;
  onSelect: () => void;
  opacity?: number;
}) {
  const footprint = useMemo(
    () => facilityFootprint(cell.coordinates, placement.areaM2 / cell.areaM2),
    [cell.coordinates, cell.areaM2, placement.areaM2]
  );
  const paved = placement.facilityType === 'PERMEABLE_PAVEMENT';
  const roof = placement.facilityType === 'GREEN_ROOF';
  const resources = useMemo(() => {
    const top: number[] = [],
      uv: number[] = [],
      sides: number[] = [],
      outline: number[] = [];
    for (const polygon of footprint.polygons)
      for (let i = 1; i < polygon.length - 1; i++)
        for (const [x, y] of [polygon[0], polygon[i], polygon[i + 1]]) {
          top.push(x, 0.36, -y);
          uv.push(x / 2, y / 2);
        }
    for (const [a, b] of footprint.boundary) {
      outline.push(a[0], 0.4, -a[1], b[0], 0.4, -b[1]);
      const vertices = [
        [a[0], 0.12, -a[1]],
        [b[0], 0.12, -b[1]],
        [b[0], 0.36, -b[1]],
        [a[0], 0.36, -a[1]],
      ];
      for (const i of [0, 1, 2, 0, 2, 3]) sides.push(...vertices[i]);
    }
    const geometry = (values: number[]) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(values, 3));
      g.computeVertexNormals();
      return g;
    };
    const surface = geometry(top);
    surface.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
    const lines = new THREE.BufferGeometry();
    lines.setAttribute('position', new THREE.Float32BufferAttribute(outline, 3));
    return { surface, sides: geometry(sides), outline: lines };
  }, [footprint]);
  const texture = useMemo(() => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 64;
    const context = canvas.getContext('2d');
    if (!context) throw new CatalogError('INVALID_DATA');
    context.fillStyle = paved ? '#96aeb1' : roof ? '#8eaa60' : '#687f48';
    context.fillRect(0, 0, 64, 64);
    context.strokeStyle = paved ? '#56777e' : '#526c3f';
    context.lineWidth = paved ? 3 : 1;
    if (paved) {
      context.strokeRect(0, 0, 32, 32);
      context.strokeRect(32, 0, 32, 32);
      context.strokeRect(-16, 32, 32, 32);
      context.strokeRect(16, 32, 32, 32);
      context.strokeRect(48, 32, 32, 32);
    } else {
      for (let i = 0; i < 24; i++) {
        context.fillStyle = i % 3 === 0 ? '#c1bf79' : '#779155';
        context.fillRect((i * 23) % 64, (i * 37) % 64, 3, 3);
      }
    }
    const result = new THREE.CanvasTexture(canvas);
    result.wrapS = result.wrapT = THREE.RepeatWrapping;
    result.colorSpace = THREE.SRGBColorSpace;
    result.anisotropy = 4;
    return result;
  }, [paved, roof]);
  const outline = useRef<THREE.LineSegments>(null);
  useLayoutEffect(() => {
    outline.current?.computeLineDistances();
  }, [resources]);
  useEffect(
    () => () => {
      Object.values(resources).forEach((g) => g.dispose());
    },
    [resources]
  );
  useEffect(() => () => texture.dispose(), [texture]);
  return (
    <group
      position={[0, cell.heightM + 0.2, 0]}
      onClick={(event) => {
        event.stopPropagation();
        onSelect();
      }}
    >
      <mesh geometry={resources.sides} receiveShadow castShadow={!preview}>
        <meshStandardMaterial
          color={paved ? '#4d7078' : '#827251'}
          roughness={1}
          transparent={preview || opacity < 1}
          opacity={(preview ? 0.45 : 1) * opacity}
          side={THREE.DoubleSide}
        />
      </mesh>
      <mesh geometry={resources.surface} receiveShadow>
        <meshStandardMaterial
          map={texture}
          roughness={1}
          transparent={preview || opacity < 1}
          opacity={(preview ? 0.55 : 1) * opacity}
          depthWrite={!preview && opacity === 1}
        />
      </mesh>
      <lineSegments ref={outline} geometry={resources.outline}>
        {preview ? (
          <lineDashedMaterial color="#214e67" dashSize={1.5} gapSize={0.9} />
        ) : (
          <lineBasicMaterial color={paved ? '#4d7078' : '#5e633d'} />
        )}
      </lineSegments>
      {!preview && !paved && <Planting footprint={footprint} roof={roof} opacity={opacity} />}
    </group>
  );
}
