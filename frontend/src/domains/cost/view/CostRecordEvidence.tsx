import { costRecordDto } from '../dto/costDto';
import { CostScope } from './CostScope';
import { useCostRecord } from '../controller/useCostRecord';

export function CostRecordEvidence({ value }: { value: unknown }) {
  const parsed = costRecordDto.safeParse(value);
  if (!parsed.success) return <p className="micro-note">원가 기록의 형식을 확인하지 못했습니다.</p>;
  const record = parsed.data;
  if (record.status === 'NOT_RECORDED')
    return (
      <p className="micro-note">설치 당시 상세 원가 미기록 · 현재 단가를 소급 적용하지 않습니다.</p>
    );
  const e = record.estimate;
  return (
    <CostScope
      source={e.source}
      quantity={e.quantityM2}
      unit={e.unitCostKrw}
      subtotal={e.budgetChargeKrw}
      recorded
    />
  );
}

export function InstallationCostRecord({ id }: { id: string }) {
  const { value, failed } = useCostRecord(id);
  if (!value)
    return (
      <p className="micro-note">
        {failed ? '원가 기록을 불러오지 못했습니다.' : '설치 당시 원가 확인 중'}
      </p>
    );
  return <CostRecordEvidence value={value} />;
}
