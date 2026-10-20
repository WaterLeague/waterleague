import { useEffect, useMemo, useState } from 'react';
import type { CityTile } from '../../city/entity/city';
import type { Population } from '../entity/urban';
import { nativeStreets } from '../service/nativeStreetService';
import { loadNativeBridges } from '../repository/nativeBridgeRepository';
import type { NativeBridgeGroup } from '../dto/nativeBridgeDto';
import { loadPopulation } from '../repository/urbanRepository';
export function useUrbanData(tiles: CityTile[], center: [number, number], distance: number) {
  const [bridges, setBridges] = useState<NativeBridgeGroup[] | undefined>(),
    [bridgeError, setBridgeError] = useState('');
  useEffect(() => {
    const request = new AbortController();
    void loadNativeBridges(request.signal)
      .then((value) => {
        if (!request.signal.aborted) setBridges(value);
      })
      .catch(() => {
        if (!request.signal.aborted) setBridgeError('교량 구조 불러오기 지연');
      });
    return () => request.abort();
  }, []);
  const visible = useMemo(() => {
    const radius = Math.max(750, distance * 0.85);
    return bridges?.filter(
      (g) =>
        g.bounds[0] <= center[0] + radius &&
        g.bounds[2] >= center[0] - radius &&
        g.bounds[1] <= center[1] + radius &&
        g.bounds[3] >= center[1] - radius
    );
  }, [bridges, center, distance]);
  const bridgeKey = visible?.map((g) => g.id).join(',');
  // 같은 구조 목록이면 카메라 이동 중 도로 버퍼와 이동체를 재생성하지 않는다.
  const roads = useMemo(() => nativeStreets(tiles, visible), [tiles, bridgeKey]);
  const parking = useMemo(
    () => ({
      lots: tiles.flatMap((tile) => tile.urban?.parkingLots ?? []),
      displayRoadWidths: [],
      routes: [],
    }),
    [tiles]
  );
  const [population, setPopulation] = useState<Population | null>(null);
  const [populationError, setPopulationError] = useState('');
  useEffect(() => {
    const request = new AbortController();
    void loadPopulation(request.signal)
      .then((value) => {
        if (!request.signal.aborted) setPopulation(value);
      })
      .catch(() => {
        if (!request.signal.aborted) setPopulationError('생활인구 공개자료 조회 지연');
      });
    return () => request.abort();
  }, []);
  return { roads, parking, population, error: bridgeError, populationError };
}
