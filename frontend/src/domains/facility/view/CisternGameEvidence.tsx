import { cisternGameDto, type CisternGameData } from '../dto/cisternGameDto';

export function CisternGameEvidence({ value }: { value: CisternGameData }) {
  const amount = (n: number) => n.toLocaleString('ko-KR', { maximumFractionDigits: 3 });
  const parsed = cisternGameDto.safeParse(value);
  const demand = parsed.success ? parsed.data.demandScenario : null;
  return (
    <div>
      <p>
        집수 지붕 {amount(value.roofCollectionAreaM2)}㎡ · 이용조 용량 {amount(value.capacityM3)}㎥
      </p>
      <p>
        시작 저류 {amount(value.initialStorageM3)}㎥ → 종료 저류 {amount(value.finalStorageM3)}㎥ ·
        유입 {amount(value.inflowM3)}㎥
      </p>
      <p>
        배수 {amount(value.drainageM3)}㎥ · 월류 {amount(value.overflowM3)}㎥ · 재이용량 미산정
      </p>
      <p>배수는 방류이며 사용량이 아닙니다. 남은 저류량은 영구 저감 점수에 가산하지 않습니다.</p>
      {value.demandScenario && !demand && <p>수요 비교의 계산 근거를 확인할 수 없습니다.</p>}
      {demand && (
        <details>
          <summary>일정 수요로 사용하는 경우 · 별도 운전 비교</summary>
          <p>선택 지붕 기준 하루 {amount(demand.demandRateM3Day * 1000)}L 수요 가정</p>
          <p>
            평가 수요 {amount(demand.demandM3 * 1000)}L · 잠재 공급{' '}
            {amount(demand.suppliedM3 * 1000)}L · 부족 {amount(demand.unmetDemandM3 * 1000)}L
          </p>
          <p>
            수요 충족{' '}
            {(demand.supplyFraction * 100).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}% ·
            월류 {amount(demand.overflowM3)}㎥ · 시작 저류 {amount(demand.initialStorageM3)}㎥ →
            종료 저류 {amount(demand.finalStorageM3)}㎥
          </p>
          <p>
            {new Date(demand.evaluationStart).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} ~{' '}
            {new Date(demand.evaluationEnd).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} KST
            · 선행·설치 이전 공급 제외
          </p>
          <p>자연배수 대신 수요에 맞춰 인출한 계산입니다. 물이 부족하면 공급량도 줄어듭니다.</p>
          <p>
            실제 사용량은 미확인입니다. 수질 처리·공급 설비·사용 후 하수 환류는 계산하지 않으며
            순위에 가산하지 않습니다.
          </p>
          <details>
            <summary>수요 근거와 가정</summary>
            <p>
              <a href={demand.source.url} target="_blank" rel="noopener noreferrer">
                {demand.source.title} (2018)
              </a>
            </p>
            <p>
              화성시 가구 수요 가정을 지붕 면적에 비례시킨 조건입니다. 현재 서울 건물의 관측
              사용량이나 실제 세대수가 아닙니다.
            </p>
            <p>
              <a href={demand.newerReview.url} target="_blank" rel="noopener noreferrer">
                용도별 수요 접근 검토 (2024)
              </a>
            </p>
            <ul>
              {demand.limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </details>
        </details>
      )}
    </div>
  );
}
