import { memo, useLayoutEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Color, InstancedMesh, Matrix4, PerspectiveCamera, Vector3 } from 'three';
import type { InfrastructureAsset } from '../entity/infrastructure';
import { infrastructureColor } from '../service/infrastructureService';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainHeight } from '../../terrain/service/terrainService';

export const InfrastructureMarkers = memo(function InfrastructureMarkers({
  assets,
  selectedId,
  terrain,
  onSelect,
}: {
  assets: InfrastructureAsset[];
  selectedId: string;
  terrain: Terrain | null;
  onSelect: (asset: InfrastructureAsset) => void;
}) {
  const mesh = useRef<InstancedMesh>(null);
  const scratch = useMemo(
    () => ({ point: new Vector3(), matrix: new Matrix4(), color: new Color() }),
    []
  );
  const positions = useMemo(
    () =>
      assets.map(
        (a) => new Vector3(a.center[0], terrainHeight(terrain, a.center) + 12, -a.center[1])
      ),
    [assets, terrain]
  );
  const last = useRef('');
  useLayoutEffect(() => {
    last.current = '';
    if (!mesh.current) return;
    assets.forEach((a, i) =>
      mesh.current!.setColorAt(
        i,
        scratch.color.set(a.id === selectedId ? '#dda62e' : infrastructureColor(a))
      )
    );
    if (mesh.current.instanceColor) mesh.current.instanceColor.needsUpdate = true;
  }, [assets, selectedId, scratch]);
  useFrame(({ camera, size }) => {
    if (!mesh.current || !(camera instanceof PerspectiveCamera)) return;
    const signature = `${camera.matrixWorld.elements.join(',')}:${size.height}`;
    if (last.current === signature) return;
    last.current = signature;
    // 참고 위치 표식의 화면 크기만 고정하며 부지 면적을 생성하지 않는다.
    const perPixel = (2 * Math.tan((camera.fov * Math.PI) / 360)) / Math.max(1, size.height);
    positions.forEach((position, i) => {
      const depth = -scratch.point.copy(position).applyMatrix4(camera.matrixWorldInverse).z;
      const radius =
        depth > camera.near ? depth * perPixel * (assets[i].id === selectedId ? 8 : 5) : 0;
      scratch.matrix.makeScale(radius, radius, radius).setPosition(position);
      mesh.current!.setMatrixAt(i, scratch.matrix);
    });
    mesh.current.instanceMatrix.needsUpdate = true;
    mesh.current.computeBoundingSphere();
  });
  if (!assets.length) return null;
  return (
    <instancedMesh
      key={assets.length}
      ref={mesh}
      args={[undefined, undefined, assets.length]}
      frustumCulled={false}
      renderOrder={20}
      userData={{ publicAssetMarker: true }}
      onClick={(event) => {
        if (event.delta > 5 || event.instanceId == null) return;
        event.stopPropagation();
        onSelect(assets[event.instanceId]);
      }}
    >
      <sphereGeometry args={[1, 8, 6]} />
      <meshBasicMaterial depthTest={false} depthWrite={false} toneMapped={false} />
    </instancedMesh>
  );
});
