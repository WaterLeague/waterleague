import { Wind } from 'lucide-react';
import { WeatherReadout } from './WeatherReadout';
import type { LiveRainfall } from '../entity/liveRainfall';
import { observationFresh } from '../service/rainEffectService';
import { weatherStatus } from '../service/weatherStatus';
export function WeatherBadge({
  value,
  districtId,
  now,
  busy,
  retry,
  error = '',
}: {
  value: LiveRainfall | null;
  districtId: string;
  now: number;
  busy: boolean;
  retry: () => void;
  error?: string;
}) {
  const weather = weatherStatus(value, districtId, now);
  const station = value?.districts.find((d) => d.districtId === districtId);
  return (
    <WeatherReadout
      weather={{ ...weather, label: busy && !value ? '날씨 확인 중' : weather.label }}
    >
      <p>{weather.detail}</p>
      {error && <p role="status">{error}</p>}
      <p>{weather.amount}</p>
      {station && station.observedAt && now - Date.parse(station.observedAt) <= 300000 && (
        <p>
          최근 1시간 {station.sixtyMinuteMm ?? '미확인'} mm · 오늘 누적 {station.dayMm ?? '미확인'}{' '}
          mm
        </p>
      )}
      {station && observationFresh(station, now) && (
        <p>
          {station.temperatureC != null && `${station.temperatureC}°C`}
          {station.windSpeedMs != null && (
            <>
              <Wind size={13} /> {station.windSpeedMs} m/s
            </>
          )}
        </p>
      )}
      <small>기상청 · 1분마다 갱신</small>
      <button disabled={busy} onClick={retry}>
        새로고침
      </button>
    </WeatherReadout>
  );
}
