const rad = Math.PI / 180;
export function solarPosition(at: number, latitude = 37.5665, longitude = 126.978) {
  const date = new Date(at);
  const year = date.getUTCFullYear();
  const day = (at - Date.UTC(year, 0, 1)) / 86400000;
  const days = (Date.UTC(year + 1, 0, 1) - Date.UTC(year, 0, 1)) / 86400000;
  // NOAA의 연중각·균시차 근사식을 UTC 기준으로 평가한다.
  const gamma = ((2 * Math.PI) / days) * (day - 0.5);
  const equation =
    229.18 *
    (0.000075 +
      0.001868 * Math.cos(gamma) -
      0.032077 * Math.sin(gamma) -
      0.014615 * Math.cos(2 * gamma) -
      0.040849 * Math.sin(2 * gamma));
  const declination =
    0.006918 -
    0.399912 * Math.cos(gamma) +
    0.070257 * Math.sin(gamma) -
    0.006758 * Math.cos(2 * gamma) +
    0.000907 * Math.sin(2 * gamma) -
    0.002697 * Math.cos(3 * gamma) +
    0.00148 * Math.sin(3 * gamma);
  const minutes = date.getUTCHours() * 60 + date.getUTCMinutes() + date.getUTCSeconds() / 60;
  const hour = (((((minutes + equation + 4 * longitude) % 1440) + 1440) % 1440) / 4 - 180) * rad;
  const lat = latitude * rad;
  const east = -Math.cos(declination) * Math.sin(hour);
  const north =
    Math.cos(lat) * Math.sin(declination) - Math.sin(lat) * Math.cos(declination) * Math.cos(hour);
  const up =
    Math.sin(lat) * Math.sin(declination) + Math.cos(lat) * Math.cos(declination) * Math.cos(hour);
  return {
    direction: [east, up, -north] as [number, number, number],
    elevation: Math.asin(Math.max(-1, Math.min(1, up))) / rad,
    azimuth: (Math.atan2(east, north) / rad + 360) % 360,
  };
}
export function daylight(elevation: number) {
  const x = Math.max(0, Math.min(1, (elevation + 6) / 16));
  return x * x * (3 - 2 * x);
}
