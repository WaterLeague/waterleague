import { useEffect, useMemo } from 'react';
import * as THREE from 'three';
import type { Terrain } from '../entity/terrain';
import { createTerrainGeometry } from '../service/terrainMeshService';
export function TerrainSurface({
  terrain,
  districtIds,
  ownDistrictId,
  selected,
}: {
  terrain: Terrain;
  districtIds?: string[];
  ownDistrictId: string | null;
  selected: string;
}) {
  const districtKey = districtIds?.slice().sort().join(',') ?? '';
  const geometry = useMemo(
    () => createTerrainGeometry(terrain, districtIds),
    [terrain, districtKey]
  );
  useEffect(() => {
    const colors = geometry.getAttribute('color') as THREE.BufferAttribute;
    const palette = ['#d5d9c6', '#9bb18a', '#81b1ba'].map((c) => new THREE.Color(c));
    const accent = new THREE.Color('#91b371'),
      other = new THREE.Color('#d4d9d0'),
      color = new THREE.Color();
    const own = terrain.districtIds.indexOf(ownDistrictId ?? '') + 1;
    const selectedIndex = terrain.districtIds.indexOf(selected) + 1;
    for (let i = 0; i < terrain.heights.length; i++) {
      color.copy(palette[terrain.cover[i]]);
      if (
        terrain.cover[i] !== 2 &&
        terrain.districts[i] &&
        terrain.districts[i] === (own || selectedIndex)
      )
        color.lerp(accent, 0.25);
      if (own && terrain.districts[i] !== own) color.lerp(other, 0.32);
      colors.setXYZW(i, color.r, color.g, color.b, 1);
    }
    colors.needsUpdate = true;
  }, [geometry, terrain, ownDistrictId, selected]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <mesh geometry={geometry} receiveShadow>
      <meshStandardMaterial vertexColors roughness={1} depthWrite />
    </mesh>
  );
}
