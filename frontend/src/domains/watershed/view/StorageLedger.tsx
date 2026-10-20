import type { z } from 'zod';
import type { storageSummaryDto } from '../dto/storageDto';
import { physicalAmount as number } from '../../physics/service/physicalValueFormat';
export function StorageLedger({
  title,
  summary,
}: {
  title: string;
  summary: z.infer<typeof storageSummaryDto>;
}) {
  return (
    <div aria-label={title}>
      <h3>{title}</h3>
      {summary.wholeRunLedger.facilities.map((f) => (
        <div key={f.id} className="watershed-facility-state">
          <strong>
            {f.id} · 설계 용량 {number(f.capacityM3)} m³
          </strong>
          <p>
            초기 {number(f.initialStorageM3)} → 최종 저류 {number(f.finalStorageM3)} m³
          </p>
          {f.nativeCapacityM3 !== undefined &&
            f.initialAvailableM3 !== undefined &&
            f.finalAvailableM3 !== undefined && (
              <p>
                계산 용량 {number(f.nativeCapacityM3)} m³ · 남은 저장 공간{' '}
                {number(f.initialAvailableM3)} → {number(f.finalAvailableM3)} m³
              </p>
            )}
          {f.reuseStatus === 'NOT_CALCULATED_NO_USE_DEMAND' && (
            <p>사용 수요 미확보 · 재이용량 미산정</p>
          )}
          <p>
            유입 {number(f.inflowM3)} m³ · 유출·월류 {number(f.outflowIncludingFloodingM3)} m³
          </p>
          <p>미연결 지표 월류 {number(f.floodingM3)} m³</p>
          <p>
            물수지 잔차 {number(f.balanceResidualM3)} m³ · 허용 {number(f.allowedResidualM3)} m³ ·{' '}
            {f.numericalStatus === 'PASSED' ? '통과' : '실패'}
          </p>
        </div>
      ))}
      <p>
        이 체적은 관망 전체 물수지에 포함됩니다. 수지 실패나 지표로 넘친 물의 미연결이 있으면 효과
        비교를 보류합니다.
      </p>
    </div>
  );
}
