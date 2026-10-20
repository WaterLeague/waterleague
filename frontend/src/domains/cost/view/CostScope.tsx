import type { CostSource } from '../dto/costDto';
import { won } from '../../game/service/gameService';
import './cost.css';

export function CostScope({
  source,
  quantity,
  unit,
  subtotal,
  recorded = false,
}: {
  source: CostSource;
  quantity: number;
  unit: number;
  subtotal: number;
  recorded?: boolean;
}) {
  return (
    <details className="cost-record">
      <summary>{recorded ? '설치 당시 원가 내역' : '참고비 내역 · 미산정 비용'}</summary>
      <dl>
        <div>
          <dt>{source.scope}</dt>
          <dd>{won(subtotal)}</dd>
        </div>
        <div>
          <dt>수량 × 참고 단가</dt>
          <dd>
            {quantity.toLocaleString('ko-KR')} m² × {won(unit)}/m²
          </dd>
        </div>
        <div>
          <dt>전체 현장 공사비</dt>
          <dd>미확정</dd>
        </div>
        <div>
          <dt>가격 기준연도 · 부가세</dt>
          <dd>미확인</dd>
        </div>
      </dl>
      {source.priceAdjustment && (
        <>
          <p>2026년 8월 가격 추정 · 잠정 공사비지수 적용</p>
          <p>
            원 단가 {won(source.priceAdjustment.originalUnitCostKrw)}/m² → {won(unit)}/m². 실제 견적
            기준월이 없어 2022년 연평균을 기준 시점으로 가정했습니다.
          </p>
          <p>
            {source.priceAdjustment.indexSeries} 지수 비율을 적용하고 최종 원 단가에서 올림했습니다.
            기준월 선택에 따른 범위는 {won(source.priceAdjustment.baseMonthSensitivityKrwPerM2[0])}~
            {won(source.priceAdjustment.baseMonthSensitivityKrwPerM2[1])}/m²이며 시장 견적 범위는
            아닙니다.
          </p>
          <a href={source.priceAdjustment.indexSourceUrl} target="_blank" rel="noreferrer">
            KICT 건설공사비지수 · 2026-09-30 공표 ↗
          </a>
        </>
      )}
      <p>포함: {source.includes.join(' · ')}</p>
      <ul aria-label="미산정 비용">
        {source.excludes.map((label, i) => (
          <li key={i}>
            {label} <span>미산정</span>
          </li>
        ))}
      </ul>
      <p>{source.note}</p>
      <p>
        미산정 항목은 무료가 아닙니다. 예산에는 참고비만 반영하며, 과거 재해 당시 가격이나 현재 확정
        견적을 뜻하지 않습니다.
      </p>
      <a href={source.sourceUrl} target="_blank" rel="noreferrer">
        {source.referenceYear}년 공개자료 · {source.sourceTitle} ↗
      </a>
    </details>
  );
}
