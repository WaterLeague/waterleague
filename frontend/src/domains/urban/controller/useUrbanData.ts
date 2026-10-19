import { useEffect, useState } from 'react';
import type { Population, Street } from '../entity/urban';
import { loadPopulation, loadStreets } from '../repository/urbanRepository';
export function useUrbanData(center: [number, number], distance: number) {
  const [roads, setRoads] = useState<Street[]>([]),
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
      void loadStreets([x, y], scale, controller.signal)
        .then((v) => {
          if (!controller.signal.aborted) {
            setRoads(v);
            setError('');
          }
        })
        .catch(() => {
          if (!controller.signal.aborted) setError('도로 자료를 불러오지 못했습니다.');
        });
    }, 150);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [x, y, scale]);
  return { roads, population, error, populationError };
}
