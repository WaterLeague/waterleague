import type { WatershedJob } from '../dto/watershedDto';
import { physicalAmount as number } from '../../physics/service/physicalValueFormat';
export function PumpOperation({ job }: { job: WatershedJob }) {
  const report = job.result?.cases.find((c) => c.id === 'strategy')?.pumpOperation;
  if (!report?.pumps.length) return null;
  return (
    <section className="watershed-facility-state" aria-label="펌프 운전 결과">
      <h4>펌프 운전 결과</h4>
      {report.pumps.map((p) => {
        const design = job.design.pumps?.placements.find((d) => 'WLPU_' + d.id === p.linkId);
        return (
          <div key={p.linkId}>
            <strong>
              {design?.id ?? p.linkId} · {design?.fromNode} → {design?.toNode}
            </strong>
            <p>
              내부 이송 {number(p.transferredM3)} m³ · 가동 {number(p.runningSeconds)}초 · 기동{' '}
              {p.startCount}회
            </p>
            <p>
              최대 펌프 유량 {number(p.peakFlowM3s)} m³/s
              {p.runningSeconds > 0 && (
                <>
                  {' '}
                  · 운전 양정 {number(p.minimumOperatingHeadM)}~{number(p.maximumOperatingHeadM)} m
                </>
              )}
            </p>
            <p>
              축에너지{' '}
              {p.shaftEnergyKwh === null
                ? '범위 이탈로 산정 보류'
                : `${number(p.shaftEnergyKwh)} kWh`}{' '}
              · 전기 사용량 미산정
            </p>
            <p>
              성능곡선 범위 이탈: 양정 {number(p.outsideHeadCurveSeconds)}초 / 유량{' '}
              {number(p.outsideFlowCurveSeconds)}초 ·{' '}
              {p.curveStatus === 'PASSED' ? '범위 검사 통과' : '실패'}
            </p>
            <p>
              토출 접속부 월류 {number(p.deliveryFloodingM3)} m³ ·{' '}
              {p.deliveryStatus === 'PASSED' ? '압력 한계 검사 통과' : '압력 한계 초과 실패'}
            </p>
          </div>
        );
      })}
      <p>
        이송량은 침수 감소량이 아닙니다. 하류 효과는 관망 전체 결과와 함께 확인하세요. 최소
        잠김·캐비테이션 안전성 미평가.
      </p>
    </section>
  );
}
