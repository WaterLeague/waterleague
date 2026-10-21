import { useMemo, useState } from 'react';
import { X, Search, MapPin } from 'lucide-react';
import type {
  InfrastructureAsset,
  InfrastructureCatalog,
  InfrastructureSource,
} from '../entity/infrastructure';
import { infrastructureNames } from '../service/infrastructureService';
import { useEquipmentHistory } from '../controller/useEquipmentHistory';
import { EquipmentHistoryPanel } from './EquipmentHistoryPanel';
import './infrastructure.css';
const number = new Intl.NumberFormat('ko-KR');
export function InfrastructureEvidence({
  asset,
  source,
  historical,
}: {
  asset: InfrastructureAsset;
  source: InfrastructureSource;
  historical: boolean;
}) {
  const spec = asset.pumpSpecs;
  const footprint = asset.footprint;
  return (
    <section className="infrastructure-evidence">
      <span className="infrastructure-kicker">{infrastructureNames[asset.kind]} · 공개 기록</span>
      <h3>{asset.name}</h3>
      <p className="infrastructure-scope">
        {historical
          ? '현재 공개자료 참고 · 재해 당시 시설로 확인되지 않음'
          : '위치 참고 · 현재 운영 상태 미확인'}
      </p>
      {spec && (
        <>
          <p>{spec.address}</p>
          <dl>
            <div>
              <dt>자료 기준일</dt>
              <dd>{spec.asOf}</dd>
            </div>
            <div>
              <dt>유역면적</dt>
              <dd>{number.format(spec.basinAreaHa)} ha</dd>
            </div>
            <div>
              <dt>유수지 용량</dt>
              <dd>{number.format(spec.storageCapacityM3)} m³</dd>
            </div>
          </dl>
          <div className="infrastructure-table">
            <table>
              <caption>호기별 공개 제원 · 실제 운전량 아님</caption>
              <thead>
                <tr>
                  <th>호기</th>
                  <th>마력 (HP)</th>
                  <th>양수량 (m³/min)</th>
                </tr>
              </thead>
              <tbody>
                {spec.units.map((unit) => (
                  <tr key={unit.unit}>
                    <td>{unit.unit}</td>
                    <td>{number.format(unit.powerHp)}</td>
                    <td>{number.format(unit.capacityM3Min)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {footprint ? (
        <>
          <dl>
            <div>
              <dt>지도 도형 면적</dt>
              <dd>{number.format(Math.round(footprint.areaM2))} m²</dd>
            </div>
            <div>
              <dt>지도 자료 시점</dt>
              <dd>{footprint.mappedAt}</dd>
            </div>
          </dl>
          <p>
            {footprint.buildingId
              ? '공개 지도에 빗물펌프장으로 등록된 건물입니다. 같은 원본 건물의 옥상 후보에는 새 게임 시설을 설치할 수 없습니다. 건물 전체 예약은 게임 설치 규칙이며 옥상의 펌프 점유를 뜻하지 않습니다.'
              : '공개 지도에 저류 영역으로 등록된 경계입니다. 겹치는 지상 후보에는 새 게임 시설을 설치할 수 없습니다. 옥상과 이전 설치 기록은 유지됩니다.'}
          </p>
          <p>
            측량·준공도와 대조되지 않았으며 용량·현재 운영·과거 존속은 미확인입니다. 물리 계산의
            시설로 포함하지 않습니다.
          </p>
          {footprint.buildingId && (
            <p>
              건물 높이 {footprint.displayHeightM} m는 기존 도시 지도 표시용 가정입니다. 실측
              높이·준공 형상이 아닙니다.
            </p>
          )}
          <a href={footprint.sourceObjectUrl} target="_blank" rel="noreferrer">
            OpenStreetMap 도형 원문 ↗
          </a>
        </>
      ) : (
        <p>
          시설 기호는 부지 경계가 아닙니다. 준공·폐지 시점과 배수 연결·운전 조건이 확인되지 않아
          물리 계산과 설치 차단에는 사용하지 않습니다.
        </p>
      )}
      <p>
        3D 시설 형태는 종류를 구별하는 기호입니다. 실제 치수·용량·운전 상태를 나타내지 않습니다.
      </p>
      <a href={source.url} target="_blank" rel="noreferrer">
        {source.publisher} · {source.title} 원문 ↗
      </a>
      <small>
        {source.license === 'ODbL-1.0'
          ? '© OpenStreetMap contributors · ODbL 1.0'
          : '공공누리 제1유형 · 출처표시'}
      </small>
      <dl>
        <div>
          <dt>포털 갱신일</dt>
          <dd>{source.portalUpdatedAt ?? '미제공'}</dd>
        </div>
      </dl>
      <details>
        <summary>자료 식별자와 원본 해시</summary>
        <p>{asset.id}</p>
        <code>{source.sha256}</code>
      </details>
    </section>
  );
}
export function InfrastructurePanel({
  catalog,
  error,
  retry,
  selectedId,
  onSelect,
  onClose,
  districtId,
  historical,
  eventId = '',
}: {
  catalog: InfrastructureCatalog | null;
  error: boolean;
  retry: () => void;
  selectedId: string;
  onSelect: (asset: InfrastructureAsset) => void;
  onClose: () => void;
  districtId: string;
  historical: boolean;
  eventId?: string;
}) {
  const history = useEquipmentHistory(eventId);
  const [search, setSearch] = useState('');
  const [allDistricts, setAllDistricts] = useState(false);
  const selected = catalog?.assets.find((a) => a.id === selectedId);
  const source = catalog?.sources.find((s) => s.id === selected?.sourceId);
  const rows = useMemo(
    () =>
      catalog?.assets.filter(
        (a) =>
          (allDistricts || !districtId || a.districtId === districtId) &&
          (!search || a.name.includes(search.trim()))
      ) ?? [],
    [catalog, districtId, allDistricts, search]
  );
  return (
    <aside
      className="infrastructure-panel"
      aria-label="공개 기존 시설"
      onKeyDown={(e) => {
        if (e.key === 'Escape') onClose();
      }}
    >
      <header>
        <div>
          <span className="infrastructure-kicker">PUBLIC INFRASTRUCTURE</span>
          <h2>공개 기존 시설</h2>
        </div>
        <button onClick={onClose} aria-label="공개 시설 닫기">
          <X size={18} />
        </button>
      </header>
      <div className="infrastructure-scroll">
        <p className="infrastructure-scope">
          {historical
            ? '현재 공개 참고 자료 · 당시 재현 입력과 분리'
            : '게임 설치와 구분된 공개 위치 자료'}
        </p>
        {error ? (
          <p role="alert">
            자료를 불러오지 못했습니다. <button onClick={retry}>다시 조회</button>
          </p>
        ) : !catalog ? (
          <p role="status">공개 자료 불러오는 중</p>
        ) : (
          <>
            {selected && source && (
              <InfrastructureEvidence asset={selected} source={source} historical={historical} />
            )}
            {history.error && (
              <p role="alert">
                설비 이력 조회 실패 <button onClick={history.retry}>다시 조회</button>
              </p>
            )}
            {selected && history.value && (
              <EquipmentHistoryPanel catalog={history.value} assetId={selected.id} />
            )}
            <label className="infrastructure-search">
              <Search size={15} />
              <input
                aria-label="공개 시설 검색"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="시설명 검색"
                maxLength={100}
              />
            </label>
            {districtId && (
              <label className="infrastructure-all">
                <input
                  type="checkbox"
                  checked={allDistricts}
                  onChange={(e) => setAllDistricts(e.target.checked)}
                />{' '}
                다른 구 자료도 검색
              </label>
            )}
            <p>{number.format(rows.length)}건 · 출처별 기록 수, 고유 시설 수 아님</p>
            <div className="infrastructure-results">
              {rows.slice(0, 80).map((a) => (
                <button key={a.id} aria-pressed={a.id === selectedId} onClick={() => onSelect(a)}>
                  <MapPin size={14} />
                  <span>
                    {a.name}
                    <small>
                      {history.value?.records.some((row) => row.record.assetId === a.id)
                        ? '설치·증설 연도 있음 · 2022 자료'
                        : a.pumpSpecs
                          ? '호기별 제원 있음 · 2025 자료'
                          : a.footprint
                            ? '지도 경계 · 운영 상태 미확인'
                            : '위치점 · 운영 상태 미확인'}
                    </small>
                  </span>
                </button>
              ))}
            </div>
            {rows.length > 80 && <p>앞의 80건 표시 · 검색어로 범위를 좁혀 주세요.</p>}
            <small>
              삭제 표시 {catalog.statusCounts.SOURCE_DELETED ?? 0}건 · 삭제 여부 결측{' '}
              {catalog.statusCounts.DELETE_FLAG_UNKNOWN ?? 0}건은 지도에서 제외했습니다. 전체
              화면에는 펌프 위치와 시설 경계를, 확대하면 주변 빗물관리 자료를 함께 표시합니다.
            </small>
            <details className="infrastructure-sources">
              <summary>자료 출처 {catalog.sources.length}건</summary>
              {catalog.sources.map((source) => (
                <p key={source.id}>
                  <a href={source.url} target="_blank" rel="noreferrer">
                    {source.publisher} · {source.title} ↗
                  </a>
                  <br />
                  {source.license === 'ODbL-1.0'
                    ? '© OpenStreetMap contributors · ODbL 1.0'
                    : '공공누리 제1유형'}{' '}
                  ·{' '}
                  {source.referenceDate
                    ? `기준일 ${source.referenceDate}`
                    : `파일 수정 ${source.fileModifiedAt ?? '미제공'}`}
                </p>
              ))}
            </details>
          </>
        )}
      </div>
    </aside>
  );
}
