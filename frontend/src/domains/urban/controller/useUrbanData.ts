import { useEffect, useMemo, useState } from 'react';
import type { CityTile } from '../../city/entity/city';
import type { Population } from '../entity/urban';
import { nativeStreets } from '../service/nativeStreetService';
import { loadNativeBridges } from '../repository/nativeBridgeRepository';
import type { NativeBridgeGroup } from '../dto/nativeBridgeDto';
import { loadPopulation } from '../repository/urbanRepository';
import { loadNativeTransport } from '../repository/nativeTransportRepository';
import type { NativeTransport } from '../dto/nativeTransportDto';
import { nativeRailStreets } from '../service/nativeTransportService';
export function useUrbanData(tiles: CityTile[], center: [number, number], distance: number) {
  const [bridges, setBridges] = useState<NativeBridgeGroup[] | undefined>(),
    [bridgeError, setBridgeError] = useState('');
  const [transport, setTransport] = useState<NativeTransport>();
  const [transportError, setTransportError] = useState('');
  useEffect(() => {
    const request = new AbortController();
    void loadNativeTransport(request.signal)
      .then((value) => {
        if (!request.signal.aborted) setTransport(value);
      })
      .catch(() => {
        if (!request.signal.aborted) setTransportError('철도·차선 자료 불러오기 지연');
      });
    return () => request.abort();
  }, []);
  const lanes = useMemo(() => new Map(transport?.lanes), [transport]);
  const railways = useMemo(() => nativeRailStreets(transport, bridges), [transport, bridges]);
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
  const nearRail = useMemo(
    () =>
      railways.filter((r) =>
        r.coordinates.some((p, i) => {
          const a = r.coordinates[Math.max(0, i - 1)],
            radius = Math.max(750, distance * 0.85);
          return (
            Math.min(a[0], p[0]) <= center[0] + radius &&
            Math.max(a[0], p[0]) >= center[0] - radius &&
            Math.min(a[1], p[1]) <= center[1] + radius &&
            Math.max(a[1], p[1]) >= center[1] - radius
          );
        })
      ),
    [railways, center, distance]
  );
  const railKey = nearRail.map((r) => r.id).join(',');
  const roads = useMemo(
    () => [...nativeStreets(tiles, visible, lanes), ...nearRail],
    [tiles, bridgeKey, lanes, railKey]
  );
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
  return { roads, parking, population, error: bridgeError || transportError, populationError };
}
