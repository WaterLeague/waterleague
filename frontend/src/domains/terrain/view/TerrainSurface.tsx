import { useEffect, useMemo } from 'react';
import * as THREE from 'three';
import type { Terrain } from '../entity/terrain';
import { otherDistrictOpacity } from '../../city/service/siteVisibilityService';
export function TerrainSurface({
  terrain,
  ownDistrictId,
  selected,
}: {
  terrain: Terrain;
  ownDistrictId: string | null;
  selected: string;
}) {
  const geometry = useMemo(() => {
    const count = terrain.width * terrain.height;
    const positions = new Float32Array(count * 3),
      colors = new Float32Array(count * 4);
    const indices: number[] = [];
    for (let i = 0; i < count; i++) {
      positions.set(
        [
          terrain.origin[0] + (i % terrain.width) * 90,
          terrain.heights[i],
          -terrain.origin[1] + Math.floor(i / terrain.width) * 90,
        ],
        i * 3
      );
      if (
        i % terrain.width < terrain.width - 1 &&
        Math.floor(i / terrain.width) < terrain.height - 1
      ) {
        const b = i + 1,
          c = i + terrain.width,
          d = c + 1;
        if (
          terrain.districts[i] ||
          terrain.districts[b] ||
          terrain.districts[c] ||
          terrain.districts[d]
        )
          indices.push(i, c, b, b, c, d);
      }
    }
    const value = new THREE.BufferGeometry();
    value.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    value.setAttribute('color', new THREE.BufferAttribute(colors, 4));
    value.setIndex(indices);
    value.computeVertexNormals();
    value.computeBoundingSphere();
    return value;
  }, [terrain]);
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
