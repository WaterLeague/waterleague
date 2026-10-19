import type { HistoricalState } from '../controller/useHistorical';
import { historicalWeather } from '../service/historicalWeather';
import { WeatherReadout } from '../../rainfall/view/WeatherReadout';

export function HistoricalWeatherBadge({
  state,
  districtId,
  districtName,
}: {
  state: HistoricalState;
  districtId: string;
  districtName: string;
}) {
  const weather = historicalWeather(state.event, state.index, districtId, districtName);
  return (
    <WeatherReadout weather={weather}>
      <p>{weather.detail}</p>
      <p>{weather.amount}</p>
      <small>기상청 · {state.event?.eventDate} · 재생 시각 기준</small>
    </WeatherReadout>
  );
}
