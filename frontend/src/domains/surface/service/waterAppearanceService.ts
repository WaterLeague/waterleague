import type { LiveRainfall } from '../../rainfall/entity/liveRainfall';
export type WaterWeather = { wind: [number, number]; rain: number; windSpeed?: number };
export const calmWater: WaterWeather = { wind: [0, 0], rain: 0 };
export function waterWeather(
  value: LiveRainfall | null,
  districtId: string,
  now: number
): WaterWeather {
  const stations =
    value?.districts.filter(
      (s) =>
        (!districtId || s.districtId === districtId) &&
        s.observedAt &&
        now - Date.parse(s.observedAt) >= 0 &&
        now - Date.parse(s.observedAt) <= 300000
    ) ?? [];
  const winds = stations.filter(
    (s) => s.windDirectionDeg != null && s.windDirectionDeg < 360 && s.windSpeedMs != null
  );
  // 기상 풍향은 불어오는 방위이므로 장면의 이동 방향과 z축을 함께 변환한다.
  const wind: [number, number] = winds.length
    ? [
        winds.reduce(
          (n, s) => n - Math.sin((s.windDirectionDeg! * Math.PI) / 180) * s.windSpeedMs!,
          0
        ) / winds.length,
        winds.reduce(
          (n, s) => n + Math.cos((s.windDirectionDeg! * Math.PI) / 180) * s.windSpeedMs!,
          0
        ) / winds.length,
      ]
    : [0, 0];
  return {
    wind,
    rain: stations.length ? Math.max(...stations.map((s) => s.oneMinuteMm ?? 0)) : 0,
    ...(winds.length
      ? { windSpeed: winds.reduce((n, s) => n + s.windSpeedMs!, 0) / winds.length }
      : {}),
  };
}

export function observedWind(
  speed: number | null | undefined,
  fromDegrees: number | null | undefined
): [number, number] {
  if (
    speed == null ||
    !Number.isFinite(speed) ||
    speed <= 0 ||
    fromDegrees == null ||
    !Number.isFinite(fromDegrees) ||
    fromDegrees < 0 ||
    fromDegrees >= 360
  )
    return [0, 0];
  const angle = (fromDegrees * Math.PI) / 180;
  return [-Math.sin(angle) * speed, Math.cos(angle) * speed];
}
