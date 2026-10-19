import { Cloud, CloudRain, CloudSnow } from 'lucide-react';
import type { ReactNode } from 'react';
import type { weatherStatus } from '../service/weatherStatus';

export function WeatherReadout({
  weather,
  children,
}: {
  weather: ReturnType<typeof weatherStatus>;
  children: ReactNode;
}) {
  const Icon = weather.kind === 'rain' ? CloudRain : weather.kind === 'snow' ? CloudSnow : Cloud;
  return (
    <details className="game-weather" data-weather={weather.kind}>
      <summary>
        <Icon size={19} />
        <span>
          {weather.place}
          <strong>{weather.label}</strong>
          <small className="weather-rain-amount">{weather.amount}</small>
        </span>
      </summary>
      <div>{children}</div>
    </details>
  );
}
