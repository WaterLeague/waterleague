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
  const place = districtId ? (stations[0]?.districtName ?? '선택 지역') : '서울 전체';
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
  const observations = stations.map((s) => {
    const age = s.observedAt ? now - Date.parse(s.observedAt) : Infinity;
    if (age >= 0 && age <= 300000 && s.oneMinuteMm != null)
      return { amount: s.oneMinuteMm, at: s.observedAt! };
    // 유효한 무강수 감지는 0으로 표시하고 관측 공백은 결측으로 유지한다.
    return observationFresh(s, now) && s.rainState === 'NO_RAIN_DETECTED'
      ? { amount: 0, at: s.rainObservedAt! }
      : null;
  });
  const known = observations.flatMap((v) => (v ? [v.amount] : []));
  const missing = stations.filter((_, i) => !observations[i]).map((s) => s.districtName);
  const selected = observations[0];
  // 강수감지 센서가 결측이어도 정상 우량계의 관측 범위를 누락으로 표시하지 않는다.
  const detail = districtId
    ? selected
      ? `${stations[0].stationName} · ${new Date(selected.at).toLocaleTimeString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false })} 기준`
      : `${stations[0]?.stationName ?? '선택 지역'} · 최신 1분 강우 미확인`
    : `강우량 ${known.length}/25개 구 확인${missing.length > 0 && missing.length <= 3 ? ` · 미확인: ${missing.join(', ')}` : ''}`;
  const number = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 2 });
  const amount = !known.length
    ? '강우량 확인 불가'
    : districtId
      ? `1분 강우 ${number.format(known[0])} mm`
      : `1분 강우 ${number.format(Math.min(...known))}${Math.max(...known) !== Math.min(...known) ? `–${number.format(Math.max(...known))}` : ''} mm${known.length < 25 ? ` · ${known.length}/25개 구` : ''}`;
  return { kind, label, place, detail, amount };
}
