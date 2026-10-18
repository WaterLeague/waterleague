import type { InitializationEvidenceData } from '../entity/initialization';
const amount = (v: number) => v.toLocaleString('ko-KR', { maximumFractionDigits: 3 });
export function InitializationEvidence({ value }: { value: InitializationEvidenceData }) {
  return (
    <div className="initialization-evidence">
      <p>
        선행 {amount((value.preActivationSeconds ?? value.warmupMinutes * 60) / 86400)}일 강우{' '}
        {amount(value.warmupRainMm)}mm와 기상으로 계산한 시작 상태입니다.{' '}
        {value.scoreExcludesWarmup
          ? '사전 기간은 점수에서 제외됩니다.'
          : '이 기록에는 사전 기간의 점수 제외가 확인되지 않았습니다.'}
      </p>
      <p>
        시작 수분율{' '}
        {value.initialSoilMoisture === null
          ? '해당 없음'
          : amount(value.initialSoilMoisture * 100) + '%'}{' '}
        · 후보 전체의 시작 수분·저류 {amount(value.initialStorageM3)}m³. 토양수분 실측값은 아닙니다.
      </p>
      {!!value.aggregateDerivedMinutes && (
        <p>
          선행 {amount(value.aggregateDerivedMinutes)}분은 관측 구간 총량의 평균 강도 적용입니다.
          분별 실측값이 아닙니다.
        </p>
      )}
      {value.limitations?.map((note) => (
        <p key={note}>{note}</p>
      ))}
      <details>
        <summary>초기화 입력 근거</summary>
        <p>
          방법: {value.method}
          {value.seed ? ` · 시작 시드: ${value.seed}` : ''}
        </p>
        {value.evaluationStart && (
          <p>
            평가 시작:{' '}
            {new Date(value.evaluationStart).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}{' '}
            KST
          </p>
        )}
        <p>
          보관 강우 원문 {value.rainfallSourceHashes?.length ?? 0}건 · 기상 원문{' '}
          {value.evaporationSourceHashes?.length ?? 0}건. 개별 해시와 입력은 계산 재현 묶음에서
          확인할 수 있습니다.
        </p>
      </details>
    </div>
  );
}
