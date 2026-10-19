import { useEffect, useState } from 'react';
import type { Population, Street } from '../entity/urban';
import { loadPopulation, loadStreets } from '../repository/urbanRepository';
import { loadParking } from '../repository/parkingRepository';
import type { ParkingData } from '../entity/parking';
import { parkingDisplayRoads } from '../service/parkingService';
export function useUrbanData(center: [number, number], distance: number) {
  const [roads, setRoads] = useState<Street[]>([]),
    [parking, setParking] = useState<ParkingData | null>(null),
    [population, setPopulation] = useState<Population | null>(null),
    [error, setError] = useState(''),
    [populationError, setPopulationError] = useState('');
  const x = Math.floor(center[0] / 1000) * 1000 + 500,
    y = Math.floor(center[1] / 1000) * 1000 + 500;
  const scale = distance > 9000 ? 10000 : distance > 2600 ? 2600 : distance > 1600 ? 1600 : 800;
  useEffect(() => {
    const controller = new AbortController();
    void loadPopulation(controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setPopulation(value);
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setPopulationError('인구 자료 연결 실패 · 일반 교통·보행 연출');
      });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void Promise.all([
        loadStreets([x, y], scale, controller.signal),
        loadParking(controller.signal),
      ])
        .then(([v, p]) => {
          if (!controller.signal.aborted) {
            setRoads(parkingDisplayRoads(v, p));
            setParking(p);
            setError('');
          }
        })
        .catch(() => {
          if (!controller.signal.aborted) setError('도로·주차장 자료를 불러오지 못했습니다.');
        });
    }, 150);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [x, y, scale]);
  return { roads, parking, population, error, populationError };
}
