import { memo, useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Color, InstancedMesh, Matrix4, PerspectiveCamera, Vector3 } from 'three';
import type { SharedInstallation } from '../entity/installation';
import { siteKey } from '../entity/installation';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainHeight } from '../../terrain/service/terrainService';
import { facilitySymbolGeometry } from '../../catalog/service/facilitySymbolService';
import { otherDistrictOpacity } from '../../city/service/siteVisibilityService';

type Props = {
  installations: SharedInstallation[];
  selectedKey: string;
  ownDistrictId: string | null;
  terrain: Terrain | null;
  onSelect: (key: string) => void;
};
const KindSymbols = memo(function KindSymbols({
  installations,
  selectedKey,
  terrain,
  onSelect,
  opacity,
}: Props & { opacity: number }) {
  const mesh = useRef<InstancedMesh>(null);
  const type = installations[0].facilityType;
  const geometry = useMemo(() => facilitySymbolGeometry(type), [type]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  const scratch = useMemo(
    () => ({ point: new Vector3(), matrix: new Matrix4(), color: new Color() }),
    []
  );
  const positions = useMemo(
    () =>
      installations.map(
        (i) =>
          new Vector3(i.center[0], terrainHeight(terrain, i.center) + i.heightM + 1, -i.center[1])
      ),
    [installations, terrain]
  );
  const last = useRef('');
  useLayoutEffect(() => {
    last.current = '';
    if (!mesh.current) return;
    installations.forEach((i, index) =>
      mesh.current!.setColorAt(
        index,
        scratch.color.set(siteKey(i) === selectedKey ? '#ffd15b' : '#ffffff')
      )
    );
    if (mesh.current.instanceColor) mesh.current.instanceColor.needsUpdate = true;
  }, [installations, positions, selectedKey, scratch]);
  useFrame(({ camera, size }) => {
    if (!mesh.current || !(camera instanceof PerspectiveCamera)) return;
    const signature = `${camera.matrixWorld.elements.join(',')}:${camera.fov}:${size.height}`;
    if (signature === last.current) return;
    last.current = signature;
    const perPixel = (2 * Math.tan((camera.fov * Math.PI) / 360)) / Math.max(1, size.height);
    positions.forEach((position, index) => {
      const depth = -scratch.point.copy(position).applyMatrix4(camera.matrixWorldInverse).z;
      const scale =
        depth > camera.near
          ? depth * perPixel * (siteKey(installations[index]) === selectedKey ? 16 : 12)
          : 0;
      mesh.current!.setMatrixAt(
        index,
        scratch.matrix.makeScale(scale, scale, scale).setPosition(position)
      );
    });
    mesh.current.instanceMatrix.needsUpdate = true;
    mesh.current.computeBoundingSphere();
  });
  return (
    <instancedMesh
      key={installations.length}
      ref={mesh}
      args={[geometry, undefined, installations.length]}
      frustumCulled={false}
      renderOrder={19}
      userData={{ installationMarker: true, symbolOnly: true, facilityKind: type }}
      onClick={(event) => {
        if (event.delta > 5 || event.instanceId == null) return;
        event.stopPropagation();
        onSelect(siteKey(installations[event.instanceId]));
      }}
    >
      <meshStandardMaterial
        vertexColors
        transparent={opacity < 1}
        opacity={opacity}
        depthTest={false}
        depthWrite={false}
        roughness={0.9}
        toneMapped={false}
      />
    </instancedMesh>
  );
});

export const InstallationSymbols = memo(function InstallationSymbols(props: Props) {
  const groups = useMemo(() => {
    const buckets = new Map<string, { installations: SharedInstallation[]; opacity: number }>();
    for (const i of props.installations) {
      const opacity =
        props.ownDistrictId && i.districtId !== props.ownDistrictId ? otherDistrictOpacity : 1;
      const key = `${i.facilityType}:${opacity}`;
      if (!buckets.has(key)) buckets.set(key, { installations: [], opacity });
      buckets.get(key)!.installations.push(i);
    }
    return [...buckets.entries()];
  }, [props.installations, props.ownDistrictId]);
  return (
    <>
      {groups.map(([key, group]) => (
        <KindSymbols key={key} {...props} {...group} />
      ))}
    </>
  );
});
