import { afterEach, expect, test, vi } from 'vitest';
import snapshot from '../../../../public/data/city-population-native-v1.json?raw';

afterEach(() => vi.unstubAllGlobals());

test('공개 생활인구의 원형 행정구 코드·결측 유지와 같은 원문 재사용', async () => {
  vi.resetModules();
  const fetcher = vi.fn(async () => new Response(snapshot));
  vi.stubGlobal('fetch', fetcher);
  const { loadPopulation } = await import('./urbanRepository');
  const signal = new AbortController().signal;
  const population = await loadPopulation(signal);
  expect(await loadPopulation(signal)).toBe(population);
  expect(fetcher).toHaveBeenCalledOnce();
  expect(Object.keys(population.event2022)).toHaveLength(50);
  expect(Object.keys(population.reference2025)).toHaveLength(175);
  for (const key of Object.keys(population.reference2025))
    expect(key).toMatch(/^[0-6]:11[0-9]{3}$/);
  expect(population.event2022['20110727:11200']).toBeUndefined();
});
