import { memo, useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Color, InstancedMesh, Matrix4, PerspectiveCamera, Vector3 } from 'three';
import type { InfrastructureAsset } from '../entity/infrastructure';
import { infrastructureSymbolGeometry } from '../service/infrastructureShapeService';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainHeight } from '../../terrain/service/terrainService';

type Props = {
  assets: InfrastructureAsset[];
  selectedId: string;
  terrain: Terrain | null;
  onSelect: (asset: InfrastructureAsset) => void;
};
const KindSymbols = memo(function KindSymbols({ assets, selectedId, terrain, onSelect }: Props) {
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
            terrainHeight(terrain, a.center) + (a.footprint?.displayHeightM ?? 0) + 3,
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
      mesh.current!.setColorAt(i, scratch.color.set(a.id === selectedId ? '#ffd15b' : '#ffffff'))
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
      const scale =
        depth > camera.near ? depth * perPixel * (assets[i].id === selectedId ? 16 : 11) : 0;
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
        depthTest={false}
        depthWrite={false}
        roughness={0.85}
        toneMapped={false}
      />
    </instancedMesh>
  );
});
export const InfrastructureMarkers = memo(function InfrastructureMarkers(props: Props) {
  const groups = useMemo(() => {
    const buckets = new Map<InfrastructureAsset['kind'], InfrastructureAsset[]>();
    props.assets.forEach((a) => {
      if (!buckets.has(a.kind)) buckets.set(a.kind, []);
      buckets.get(a.kind)!.push(a);
    });
    return [...buckets.entries()];
  }, [props.assets]);
  return (
    <>
      {groups.map(([kind, assets]) => (
        <KindSymbols key={kind} {...props} assets={assets} />
      ))}
    </>
  );
});
