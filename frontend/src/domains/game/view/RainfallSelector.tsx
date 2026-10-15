import { CloudRain } from 'lucide-react';
import type { Lab, RainfallCatalog } from '../entity/game';
export const rainDate = (value: string) =>
  new Date(value).toLocaleDateString('ko-KR', { timeZone: 'Asia/Seoul' });
export const rainTime = (value: string) =>
  new Date(value).toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul',
    dateStyle: 'short',
    timeStyle: 'short',
    hour12: false,
  });
export function RainfallSelector({
  lab,
  catalog,
  disabled,
  onChange,
}: {
  lab: Lab;
  catalog: RainfallCatalog;
  disabled: boolean;
  onChange: (hash: string) => void;
}) {
  return (
    <section className="rainfall-context" aria-label="강우 실험 조건">
      <CloudRain size={21} />
      <label>
        관측 강우
        <select
          aria-label="관측 강우 선택"
          value={lab.modelHash}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        >
          {catalog.models.map((item) => (
            <option key={item.modelHash} value={item.modelHash}>
              {item.rainfall.stationName} {item.rainfall.stationId} ·{' '}
              {rainDate(item.rainfall.start)} · {item.rainfall.totalDepthMm} mm
            </option>
          ))}
        </select>
      </label>
      <p>
        배치는 다른 비에서도 비교할 수 있습니다.
        <br />
        <span>저장·계산·순위는 선택한 조건별로 구분됩니다.</span>
      </p>
      <span className="rainfall-grade">탐색 모델 · 현장 미검증</span>
    </section>
  );
}
