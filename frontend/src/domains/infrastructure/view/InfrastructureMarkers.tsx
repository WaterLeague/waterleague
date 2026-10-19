import { memo, useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import { Color, InstancedMesh, Matrix4, PerspectiveCamera, Vector3 } from 'three';
import type { InfrastructureAsset } from '../entity/infrastructure';
import { infrastructureSymbolGeometry } from '../service/infrastructureShapeService';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainHeight } from '../../terrain/service/terrainService';
import { infrastructureColor, infrastructureMarkers } from '../service/infrastructureService';

type Props = {
  assets: InfrastructureAsset[];
  selectedId: string;
  terrain: Terrain | null;
  onSelect: (asset: InfrastructureAsset) => void;
  distance: number;
};
const KindSymbols = memo(function KindSymbols({
  assets,
  selectedId,
  terrain,
  onSelect,
  distance,
}: Props) {
  const mesh = useRef<InstancedMesh>(null);
  const geometry = useMemo(() => infrastructureSymbolGeometry(assets[0].kind), [assets[0].kind]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  const scratch = useMemo(
    () => ({ point: new Vector3(), matrix: new Matrix4(), color: new Color() }),
    []
  );
  const positions = useMemo(
    () =>
      assets.map(
        (a) =>
          new Vector3(
            a.center[0],
            terrainHeight(terrain, a.center) + (a.footprint?.displayHeightM ?? 0) + 0.8,
            -a.center[1]
          )
      ),
    [assets, terrain]
  );
  const last = useRef('');
  useLayoutEffect(() => {
    last.current = '';
    if (!mesh.current) return;
    assets.forEach((a, i) =>
      mesh.current!.setColorAt(i, scratch.color.set(a.id === selectedId ? '#ffd15b' : '#c5a7ff'))
    );
    if (mesh.current.instanceColor) mesh.current.instanceColor.needsUpdate = true;
  }, [assets, selectedId, scratch]);
  useFrame(({ camera, size }) => {
    if (!mesh.current || !(camera instanceof PerspectiveCamera)) return;
    const signature = `${camera.matrixWorld.elements.join(',')}:${camera.fov}:${size.height}`;
    if (last.current === signature) return;
    last.current = signature;
    const perPixel = (2 * Math.tan((camera.fov * Math.PI) / 360)) / Math.max(1, size.height);
    positions.forEach((position, i) => {
      const depth = -scratch.point.copy(position).applyMatrix4(camera.matrixWorldInverse).z;
      let scale =
        depth > camera.near ? depth * perPixel * (assets[i].id === selectedId ? 16 : 11) : 0;
      if (distance < 1600) scale = Math.min(scale, assets[i].footprint?.buildingId ? 2 : 4);
      scratch.matrix.makeScale(scale, scale, scale).setPosition(position);
      mesh.current!.setMatrixAt(i, scratch.matrix);
    });
    mesh.current.instanceMatrix.needsUpdate = true;
    mesh.current.computeBoundingSphere();
  });
  return (
    <instancedMesh
      key={assets.length}
      ref={mesh}
      args={[geometry, undefined, assets.length]}
      frustumCulled={false}
      renderOrder={20}
      userData={{ publicAssetMarker: true, symbolOnly: true, facilityKind: assets[0].kind }}
      onClick={(event) => {
        if (event.delta > 5 || event.instanceId == null) return;
        event.stopPropagation();
        onSelect(assets[event.instanceId]);
      }}
    >
      <meshStandardMaterial
        vertexColors
        depthTest={distance < 1600 && !!assets[0].footprint?.buildingId}
        depthWrite={false}
        roughness={0.85}
        toneMapped={false}
      />
    </instancedMesh>
  );
});
export const InfrastructureMarkers = memo(function InfrastructureMarkers(props: Props) {
  const markers = useMemo(
    () => infrastructureMarkers(props.assets, props.distance, props.selectedId),
    [props.assets, props.distance, props.selectedId]
  );
  const groups = useMemo(() => {
    const buckets = new Map<string, InfrastructureAsset[]>();
    markers.forEach((a) => {
      const key = `${a.kind}:${a.footprint?.buildingId ? 'building' : 'point'}`;
      if (!buckets.has(key)) buckets.set(key, []);
      buckets.get(key)!.push(a);
    });
    return [...buckets.entries()];
  }, [markers]);
  return (
    <>
      {groups.map(([kind, assets]) => (
        <KindSymbols key={kind} {...props} assets={assets} />
      ))}
      {markers
        .filter((a) => (a.clusterCount ?? 0) > 1)
        .map((a) => (
          <Html
            key={a.id}
            center
            position={[
              a.center[0],
              terrainHeight(props.terrain, a.center) + (a.footprint?.displayHeightM ?? 0) + 2,
              -a.center[1],
            ]}
            zIndexRange={[10, 0]}
          >
            <button
              className="infrastructure-cluster"
              style={{ background: infrastructureColor(a) }}
              onClick={() => props.onSelect(a)}
              aria-label={`공개 시설 ${a.clusterCount}개 · 확대해서 보기`}
            >
              {a.clusterCount}
            </button>
          </Html>
        ))}
    </>
  );
});
