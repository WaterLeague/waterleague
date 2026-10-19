import type { Population } from '../entity/urban';
export function populationAt(
  data: Population | null,
  at: number,
  district: string,
  historical: boolean
) {
  if (!data) return null;
  const kst = new Date(at + 9 * 3600000);
  const hour = kst.getUTCHours();
  const day = kst.toISOString().slice(0, 10).replaceAll('-', '');
  const values = historical
    ? data.event2022[`${day}:${district}`]
    : data.reference2025[`${(kst.getUTCDay() + 6) % 7}:${district}`];
  if (!values || values[hour] == null) return null;
  return {
    people: values[hour],
    evidence: historical ? 'ARCHIVED_2022' : 'REFERENCE_2025',
  } as const;
}
export function displayDensity(people: number | undefined, areaKm2: number) {
  // 생활인구를 개별 차량·보행자의 관측으로 변환하지 않고 표시 예산만 비례 배분한다.
  return people == null
    ? 0.3
    : Math.max(0.08, Math.min(2, people / Math.max(0.001, areaKm2) / 15000));
}
