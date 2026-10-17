import type { EquipmentHistoryCatalog } from '../dto/equipmentHistoryDto';

const labels = {
  SOURCE_REFERENCE: '자료 기준일의 설비 기록',
  NOT_INSTALLED_YET: '사건 이후 설치 · 당시 설비에서 제외',
  INSTALLATION_DATE_UNCERTAIN: '사건과 설치연도 동일 · 설치일 미확인',
  LATER_EXPANSION: '사건 이후 증설 · 이전 제원 미확인',
  EXPANSION_DATE_UNCERTAIN: '사건과 증설연도 동일 · 증설일 미확인',
  INSTALLATION_PRECEDES_EVENT: '설치연도상 선행 · 당시 존속·운전 미확인',
};

export function EquipmentHistoryPanel({
  catalog,
  assetId,
}: {
  catalog: EquipmentHistoryCatalog;
  assetId: string;
}) {
  const rows = catalog.records.filter((row) => row.record.assetId === assetId);
  if (!rows.length) return null;
  return (
    <section className="infrastructure-history" aria-label="공개 설비 이력">
      <h4>설치·증설 이력{catalog.eventDate ? ` · ${catalog.eventDate} 기준` : ''}</h4>
      <p>{rows[0].record.address}</p>
      <p>2022-01-18 자료 · 행별 설비 묶음. 현재 제원과 과거 제원은 같다고 볼 수 없습니다.</p>
      <ol>
        {rows.map(({ record: row, temporalStatus, sourcePrecedesEvent }) => (
          <li key={row.id}>
            <strong>
              {row.installedYear}년 설치
              {row.expandedYear ? ` · ${row.expandedYear}년 증설` : ' · 증설연도 미제공'}
            </strong>
            <span className={temporalStatus === 'NOT_INSTALLED_YET' ? 'equipment-excluded' : ''}>
              {labels[temporalStatus]}
            </span>
            {sourcePrecedesEvent && <span>사건이 자료 기준일 이후 · 제원 변경 여부 미확인</span>}
            <small>
              원문 규모 {row.motorSizeRaw} {row.sizeUnitRaw} · 모터 {row.motorCount}대
              {row.engineCount > 0 &&
                ` · 엔진 ${row.engineSizeRaw} ${row.sizeUnitRaw} ${row.engineCount}대`}
            </small>
            <small>원문 {row.sourceRow}행 · 혼합 단위 표기, 양수량으로 변환하지 않음</small>
          </li>
        ))}
      </ol>
      <p>
        위치 연결은 구·시설명 대조에 따른 참고 관계입니다. 부지 경계·배수 연결·운전 조건은
        미확인으로 물리 계산에 포함하지 않습니다.
      </p>
      <a href={catalog.source.url} target="_blank" rel="noreferrer">
        광진구 설비 이력 원문 ↗
      </a>
      <small>이용허락 제한 없음 · 원문 SHA-256 {catalog.source.sha256}</small>
    </section>
  );
}
