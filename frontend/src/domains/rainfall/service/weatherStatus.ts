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
          : '강수감지 미확인';
  const detail =
    districtId && fresh[0]
      ? `${fresh[0].stationName} · ${new Date(fresh[0].rainObservedAt!).toLocaleTimeString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false })} 기준`
      : `${fresh.filter((s) => s.rainState !== 'UNKNOWN').length}/${districtId ? 1 : 25}개 구 최신 상태 확인`;
  const amounts = stations.map((s) => {
    const age = s.observedAt ? now - Date.parse(s.observedAt) : Infinity;
    if (age >= 0 && age <= 300000 && s.oneMinuteMm != null) return s.oneMinuteMm;
    // 유효한 무강수 감지는 0으로 표시하고 관측 공백은 결측으로 유지한다.
    return observationFresh(s, now) && s.rainState === 'NO_RAIN_DETECTED' ? 0 : null;
  });
  const known = amounts.filter((v): v is number => v !== null);
  const number = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 2 });
  const amount = !known.length
    ? '강우량 확인 불가'
    : districtId
      ? `1분 강우 ${number.format(known[0])} mm`
      : `1분 강우 ${number.format(Math.min(...known))}${Math.max(...known) !== Math.min(...known) ? `–${number.format(Math.max(...known))}` : ''} mm${known.length < 25 ? ` · ${known.length}/25개 구` : ''}`;
  return { kind, label, place, detail, amount };
}
