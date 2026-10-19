import type { LiveRainfall } from '../entity/liveRainfall';
import { observationFresh } from './rainEffectService';
export function weatherStatus(value: LiveRainfall | null, districtId: string, now: number) {
  const stations = districtId
    ? (value?.districts.filter((d) => d.districtId === districtId) ?? [])
    : (value?.districts ?? []);
  const fresh = stations.filter((s) => observationFresh(s, now));
  const rain = fresh.filter((s) => s.rainState === 'WET');
  const snow = fresh.filter((s) => s.rainState === 'SNOW');
  const dry = fresh.filter((s) => s.rainState === 'NO_RAIN_DETECTED');
  const place = districtId ? (stations[0]?.districtName ?? '선택 지역') : '서울';
  const complete = stations.length === (districtId ? 1 : 25) && dry.length === stations.length;
  const kind = rain.length ? 'rain' : snow.length ? 'snow' : complete ? 'dry' : 'unknown';
  const label =
    kind === 'rain'
      ? districtId
        ? '비 오는 중'
        : `${rain.length}개 구 비`
      : kind === 'snow'
        ? districtId
          ? '눈 오는 중'
          : `${snow.length}개 구 눈`
        : kind === 'dry'
          ? '비·눈 없음'
          : '날씨 확인 필요';
  const detail =
    districtId && fresh[0]
      ? `${fresh[0].stationName} · ${new Date(fresh[0].rainObservedAt!).toLocaleTimeString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false })} 기준`
      : `${fresh.filter((s) => s.rainState !== 'UNKNOWN').length}/${districtId ? 1 : 25}개 구 최신 상태 확인`;
  return { kind, label, place, detail };
}
