import { memo, useEffect, useMemo } from 'react';
import { BufferAttribute, Color, ShapeGeometry } from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import type { City } from '../../city/entity/city';
import type { Terrain } from '../../terrain/entity/terrain';
import { polygonShapes } from '../../catalog/service/mapGeometryService';
import { terrainHeight } from '../../terrain/service/terrainService';
import type { WaterWeather } from '../service/waterAppearanceService';
import { WaterMaterial } from './WaterMaterial';
export const RiverLayer = memo(function RiverLayer({
  city,
  terrain,
  animate,
  weather,
}: {
  city: City;
  terrain: Terrain | null;
  animate: boolean;
  weather: WaterWeather;
}) {
  const geometry = useMemo(() => {
    const parts = city.surfaces
      .filter((s) => s.kind === 'water')
      .map((s) => {
        const g = new ShapeGeometry(polygonShapes(s.polygons));
        const p = g.getAttribute('position');
        const colors = new Float32Array(p.count * 3),
          color = new Color('#358caa');
        for (let i = 0; i < p.count; i++) {
          const x = p.getX(i),
            y = p.getY(i);
          p.setXYZ(i, x, terrainHeight(terrain, [x, y]) + 2, -y);
          colors.set(color.toArray(), i * 3);
        }
        g.setAttribute('color', new BufferAttribute(colors, 3));
        g.setAttribute('flow', new BufferAttribute(new Float32Array(p.count * 2), 2));
        return g;
      });
    if (!parts.length) return null;
    const merged = mergeGeometries(parts);
    parts.forEach((g) => g.dispose());
    merged?.computeBoundingSphere();
    return merged;
  }, [city, terrain]);
  useEffect(() => () => geometry?.dispose(), [geometry]);
  return geometry ? (
    <mesh geometry={geometry} renderOrder={3} raycast={() => {}} userData={{ naturalWater: true }}>
      <WaterMaterial natural animate={animate} weather={weather} />
    </mesh>
  ) : null;
});
