import type { CisternGameData } from '../dto/cisternGameDto';

export function CisternGameEvidence({ value }: { value: CisternGameData }) {
  const amount = (n: number) => n.toLocaleString('ko-KR', { maximumFractionDigits: 3 });
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
    </div>
  );
}
