import { describe, expect, it } from 'vitest';
import snapshot from '../../../../public/data/seoul-native-v1/city.json';
import { mapCity, mapCityTile } from '../mapper/cityMapper';
import { nearbyTiles } from './cityService';
const city = mapCity(snapshot);
describe('서울 전역 자료와 부분 로딩', () => {
  it('전체 보기에서는 타일을 요청하지 않고 주변 요청에 상한 적용', () => {
    expect(nearbyTiles(city, [0, 0], 35000)).toEqual([]);
    expect(nearbyTiles(city, [NaN, 0], 1000)).toEqual([]);
    expect(nearbyTiles(city, [55000, 55000], 1000)).toEqual([]);
    for (const district of city.districts) {
      const tiles = nearbyTiles(city, district.center, 4800);
      expect(tiles.length).toBeGreaterThan(0);
      expect(tiles.length).toBeLessThanOrEqual(16);
      expect(tiles.reduce((sum, tile) => sum + tile.buildingCount, 0)).toBeLessThanOrEqual(
        Math.max(28000, tiles[0].buildingCount)
      );
      expect(nearbyTiles(city, district.center, 4800)).toEqual(tiles);
    }
  });
  it('건물 타일의 식별자·건수·잘못된 높이 거부', () => {
    const data = {
      schemaVersion: 2,
      id: '0_0',
      buildings: [structuredClone(city.overviewBuildings[0])],
      nativeFeatures: [],
    };
    expect(mapCityTile(data, '0_0', 1).buildings).toHaveLength(1);
    expect(() => mapCityTile(data, 'wrong', 1)).toThrow();
    expect(() => mapCityTile(data, '0_0', 2)).toThrow();
    data.buildings[0].heightM = -1;
    expect(() => mapCityTile(data, '0_0', 1)).toThrow();
  });
});
