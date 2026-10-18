import { useEffect, useMemo } from 'react';
import * as THREE from 'three';
import type { Terrain } from '../entity/terrain';
import { otherDistrictOpacity } from '../../city/service/siteVisibilityService';
import { createTerrainGeometry } from '../service/terrainMeshService';
export function TerrainSurface({
  terrain,
  ownDistrictId,
  selected,
}: {
  terrain: Terrain;
  ownDistrictId: string | null;
  selected: string;
}) {
  const geometry = useMemo(() => createTerrainGeometry(terrain), [terrain]);
  useEffect(() => {
    const colors = geometry.getAttribute('color') as THREE.BufferAttribute;
    const palette = ['#d5d9c6', '#9bb18a', '#81b1ba'].map((c) => new THREE.Color(c));
    const accent = new THREE.Color('#91b371'),
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
      colors.setXYZW(
        i,
        color.r,
        color.g,
        color.b,
        own && terrain.districts[i] !== own ? otherDistrictOpacity : 1
      );
    }
    colors.needsUpdate = true;
  }, [geometry, terrain, ownDistrictId, selected]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <mesh geometry={geometry} receiveShadow>
      <meshStandardMaterial
        vertexColors
        roughness={1}
        transparent={!!ownDistrictId}
        depthWrite={!ownDistrictId}
      />
    </mesh>
  );
}
