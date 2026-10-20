import { useEffect, useMemo, useState } from 'react';
import type { CityTile } from '../../city/entity/city';
import type { Population } from '../entity/urban';
import type { ParkingData } from '../entity/parking';
import { nativeStreets } from '../service/nativeStreetService';
import { loadPopulation } from '../repository/urbanRepository';
export function useUrbanData(tiles: CityTile[]) {
  const roads = useMemo(() => nativeStreets(tiles), [tiles]);
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
  return { roads, parking: null as ParkingData | null, population, error: '', populationError };
}
