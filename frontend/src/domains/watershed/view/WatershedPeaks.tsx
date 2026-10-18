import type { WatershedMetrics } from '../dto/watershedMetricsDto';
import { physicalAmount as number } from '../../physics/service/physicalValueFormat';
const elapsed = (seconds: number) => {
  const ms = Math.round(seconds * 1000);
  return `${Math.floor(ms / 3600000)}시간 ${Math.floor(ms / 60000) % 60}분 ${((ms % 60000) / 1000).toLocaleString('ko-KR', { maximumFractionDigits: 3 })}초`;
};
export function WatershedPeaks({
  baseline,
  strategy,
  reduction,
}: {
  baseline: WatershedMetrics;
  strategy: WatershedMetrics;
  reduction: number;
}) {
  return (
    <section aria-label="고정 외부 출구 첨두 비교">
      <div
        className="watershed-effect"
        data-direction={reduction < 0 ? 'increase' : reduction > 0 ? 'decrease' : 'equal'}
      >
        <span>외부 출구 동시 합계 첨두</span>
        <strong>
          {number(Math.abs(reduction))} m³/s{' '}
          {reduction < 0 ? '증가' : reduction > 0 ? '감소' : '변화 없음'}
        </strong>
        <small>
          기준 {number(baseline.combined.peakOutwardM3s)} → 설계{' '}
          {number(strategy.combined.peakOutwardM3s)} m³/s
        </small>
        <small>기준 − 설계: {number(reduction)} m³/s</small>
      </div>
      <details>
        <summary>출구별 최대 유량·발생 시각</summary>
        <p>
          시각은 계산 시작부터의 경과 시간입니다. 출구별 첨두는 발생 시각이 달라 단순 합산하지
          않습니다.
        </p>
        <p>
          동시 합계 첨두 시각: 기준 {elapsed(baseline.combined.peakOutwardTimeSeconds)} / 설계{' '}
          {elapsed(strategy.combined.peakOutwardTimeSeconds)}
        </p>
        {baseline.specification.networkOutfalls.map((id) => {
          const b = baseline.outfalls[id],
            s = strategy.outfalls[id];
          return (
            <div className="watershed-case" key={id}>
              <strong>{id}</strong>
              <p>
                최대 방류: 기준 {number(b.peakOutwardM3s)} → 설계 {number(s.peakOutwardM3s)} m³/s
              </p>
              <p>
                기준 {elapsed(b.peakOutwardTimeSeconds)} / 설계 {elapsed(s.peakOutwardTimeSeconds)}
              </p>
              <p>
                역류 체적: 기준 {number(b.inwardVolumeM3)} → 설계 {number(s.inwardVolumeM3)} m³
              </p>
            </div>
          );
        })}
        <p>
          엔진 내부 단계에서 측정한 연구 관망의 유량입니다. 실제 하류 침수 위험의 확정값이 아닙니다.
        </p>
      </details>
    </section>
  );
}
