import type { MapScope } from '../../../shared/service/mapScope';
import { startTransition, useEffect, useMemo, useRef, useState } from 'react';
import type { CityTile } from '../../city/entity/city';
import type { Population } from '../entity/urban';
import { loadPopulation } from '../repository/urbanRepository';
import { UrbanRoadSession, type UrbanRoads } from '../repository/urbanRoadRepository';
export function useUrbanData(
  tiles: CityTile[],
  center: [number, number],
  distance: number,
  scope?: MapScope
) {
  const [data, setData] = useState<UrbanRoads>({ roads: [], railTraffic: [], railServices: [] });
  const [error, setError] = useState('');
  const session = useRef<UrbanRoadSession | null>(null);
  useEffect(() => {
    const current = new UrbanRoadSession(
      (value) => {
        setError('');
        startTransition(() => setData(value));
      },
      () => setError('교량·도로·철도 자료 불러오기 지연')
    );
    session.current = current;
    return () => {
      current.dispose();
      session.current = null;
    };
  }, []);
  useEffect(() => {
    session.current?.update(tiles, center, distance, scope);
  }, [tiles, center, distance, scope]);
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
  return {
    roads: data.roads,
    railTraffic: data.railTraffic,
    railServices: data.railServices,
    parking,
    population,
    error,
    populationError,
  };
}
