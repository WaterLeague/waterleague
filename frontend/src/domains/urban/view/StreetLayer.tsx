import { scenePointer, clearScenePointer } from '../../city/service/mapCursor';
import { buildingRaycast } from '../../city/service/buildingRaycastService';
import { requestStreetMesh } from '../repository/streetGeometryRepository';
import type { StreetBuffers } from '../service/streetMeshService';
import { Sphere, Vector3 } from 'three';
import { streetAtFace } from '../service/streetGeometryService';
import { memo, useEffect, useState } from 'react';
import { BufferAttribute, BufferGeometry, DoubleSide } from 'three';
import type { Street } from '../entity/urban';
import type { Terrain } from '../../terrain/entity/terrain';
import type { ParkingData } from '../entity/parking';
export const StreetLayer = memo(function StreetLayer({
  roads,
  terrain,
  detail,
  center,
  parking,
  onStreet,
}: {
  roads: Street[];
  terrain: Terrain | null;
  detail: boolean;
  center?: [number, number];
  parking?: ParkingData | null;
  onStreet?: (sourceId: string, point: [number, number]) => void;
}) {
  const [geometry, setGeometry] = useState<BufferGeometry | null>(null);
  const [failed, setFailed] = useState(false);
  const centerX = detail && center ? Math.round(center[0] / 500) * 500 : undefined;
  const centerY = detail && center ? Math.round(center[1] / 500) * 500 : undefined;
  useEffect(() => () => geometry?.dispose(), [geometry]);
  useEffect(() => {
    setFailed(false);
    const request = new AbortController();
    const apply = (data: StreetBuffers) => {
      if (request.signal.aborted) return;
      const mesh = new BufferGeometry();
      mesh.setAttribute('position', new BufferAttribute(data.positions, 3));
      mesh.setAttribute('color', new BufferAttribute(data.colors, 3));
      mesh.setAttribute('normal', new BufferAttribute(data.normals, 3));
      mesh.userData.streetEnds = data.ends;
      mesh.userData.streetIds = roads.map((road) => road.id);
      mesh.userData.raycast = buildingRaycast(data);
      mesh.boundingSphere = new Sphere(new Vector3(...data.sphere.slice(0, 3)), data.sphere[3]);
      setGeometry(mesh);
    };
    void requestStreetMesh(
      roads,
      terrain,
      detail,
      parking?.routes
        .filter((route) => route.reason === 'OSM_PARKING_AISLE')
        .map((route) => route.id) ?? [],
      centerX !== undefined && centerY !== undefined ? [centerX, centerY] : undefined,
      request.signal
    )
      .then(apply)
      .catch(() => {
        if (!request.signal.aborted) setFailed(true);
      });
    return () => request.abort();
  }, [roads, terrain, detail, parking, centerX, centerY]);
  if (failed) throw new Error('도로 표시 실패');
  return geometry ? (
    <mesh
      geometry={geometry}
      onPointerMove={onStreet ? (event) => scenePointer(event, 'install') : undefined}
      onPointerOut={clearScenePointer}
      receiveShadow
      raycast={onStreet ? geometry.userData.raycast : () => {}}
      onClick={
        onStreet
          ? (event) => {
              if (event.delta > 4) return;
              const index = streetAtFace(geometry.userData.streetEnds, event.faceIndex ?? -1);
              if (index < 0) return;
              event.stopPropagation();
              onStreet(geometry.userData.streetIds[index], [event.point.x, -event.point.z]);
            }
          : undefined
      }
    >
      <meshStandardMaterial
        vertexColors
        roughness={0.95}
        side={DoubleSide}
        polygonOffset
        polygonOffsetFactor={-1}
        polygonOffsetUnits={-1}
      />
    </mesh>
  ) : null;
});
