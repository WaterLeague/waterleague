import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import type { WatershedState } from '../controller/useWatershed';
import { NetworkDesignForm } from './NetworkDesignForm';
import { StorageDesignForm } from './StorageDesignForm';
import { ConduitDesignForm } from './ConduitDesignForm';
import { CisternDesignForm } from './CisternDesignForm';
import { PumpDesignForm } from './PumpDesignForm';
import { jobLabels, WatershedResult } from './WatershedResult';
const types = {
  BIORETENTION: '생물저류',
  INFILTRATION_TRENCH: '침투도랑',
  VEGETATIVE_SWALE: '식생수로',
  RAINWATER_CISTERN: '빗물이용조',
  UNDERGROUND_STORAGE: '지하 저류조',
  CONDUIT: '관로 개량',
  PUMP_STATION: '펌프장',
} as const;
export function ConnectedWatershedPanel({
  state,
  selectedId,
  onSelect,
  onClose,
  onLogin,
  onLocate,
  onMapSelection,
}: {
  state: WatershedState;
  selectedId: string;
  onSelect: (id: string) => void;
  onClose: () => void;
  onLogin: () => void;
  onLocate: () => void;
  onMapSelection: (enabled: boolean) => void;
}) {
  const [type, setType] = useState<keyof typeof types>('BIORETENTION');
  useEffect(() => {
    onMapSelection(['BIORETENTION', 'INFILTRATION_TRENCH', 'VEGETATIVE_SWALE'].includes(type));
  }, [type, onMapSelection]);
  const catalog = state.catalog,
    geo = catalog?.georeference;
  const selected = geo?.comparison.find((c) => c.sourceCrsHypothesis === geo.assumedSourceCrs);
  return (
    <aside className="shared-inspector watershed-panel" aria-label="서초 연결 유역 설계">
      <header className="watershed-heading">
        <h2>서초 연결 유역 설계</h2>
        <button onClick={onClose} aria-label="연결 유역 설계 닫기">
          <X size={18} />
        </button>
      </header>
      <p>공개 연구 모형의 14개 집수구역과 26개 관로를 함께 계산합니다.</p>
      <p className="watershed-warning">
        지도 위치는 공개 도로 대조에 근거한 가정입니다. 출판 모형의 2010년 강우·추정 외부 유입으로
        비교하며, 현재 주간·재해 점수에는 합산하지 않습니다.
      </p>
      {!state.allowed ? (
        <>
          <p>회원으로 로그인하면 지도에서 집수구역을 선택하고 설계를 계산할 수 있습니다.</p>
          <button className="watershed-submit" onClick={onLogin}>
            로그인
          </button>
        </>
      ) : (
        <>
          {state.loading && !catalog && <p role="status">관망 자료와 내 계산 조회 중…</p>}
          {state.error && (
            <p role="alert">
              {state.error} <button onClick={state.retry}>다시 조회</button>
            </p>
          )}
          {catalog && (
            <>
              {geo && (
                <button className="watershed-all-candidates" onClick={onLocate}>
                  지도에서 유역 전체 보기
                </button>
              )}
              <label>
                비교할 시설
                <select
                  value={type}
                  disabled={state.busy}
                  onChange={(e) => setType(e.target.value as keyof typeof types)}
                >
                  {Object.entries(types).map(([id, label]) => (
                    <option key={id} value={id}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <p>
                {['BIORETENTION', 'INFILTRATION_TRENCH', 'VEGETATIVE_SWALE'].includes(type)
                  ? '지도나 아래 관망도에서 집수구역을 선택하세요.'
                  : '아래 원본 관망도와 연결 목록에서 설계 대상을 선택하세요.'}
              </p>
              {type === 'UNDERGROUND_STORAGE' ? (
                <StorageDesignForm catalog={catalog} state={state} />
              ) : type === 'CONDUIT' ? (
                <ConduitDesignForm catalog={catalog} state={state} />
              ) : type === 'PUMP_STATION' ? (
                <PumpDesignForm catalog={catalog} state={state} />
              ) : type === 'RAINWATER_CISTERN' ? (
                <CisternDesignForm catalog={catalog} state={state} />
              ) : (
                <NetworkDesignForm
                  type={type}
                  catalog={catalog}
                  state={state}
                  selectedCatchmentId={selectedId}
                  onSelectCatchment={onSelect}
                />
              )}
              {geo && (
                <details className="watershed-source">
                  <summary>위치 가정과 원 자료</summary>
                  <p>
                    가정 좌표계 {geo.assumedSourceCrs} · 도로 자료{' '}
                    {geo.roadSource.distributionUpdatedAt}
                  </p>
                  <p>
                    도로 중심선과 절점의 평균 거리 {selected?.nodes.meanM?.toFixed(2)}m, 최대{' '}
                    {selected?.nodes.maxM?.toFixed(2)}m. 관로 표본의 길이 가중 평균{' '}
                    {selected?.conduits.lengthWeightedMeanM?.toFixed(2)}m.
                  </p>
                  {geo.limitations.map((v) => (
                    <p key={v}>{v}</p>
                  ))}
                  <a href={geo.sourceUrl} target="_blank" rel="noreferrer">
                    공개 연구 관망 원본
                  </a>
                  <p>
                    {catalog.catalog.attribution.authors.join(' · ')} ·{' '}
                    {catalog.catalog.licence.short_name}
                  </p>
                </details>
              )}
            </>
          )}
          {state.jobs.length > 0 && (
            <label>
              내 최근 연결 계산
              <select value={state.job?.id ?? ''} onChange={(e) => state.selectJob(e.target.value)}>
                {state.jobs.map((j) => (
                  <option value={j.id} key={j.id}>
                    {new Date(j.createdAt).toLocaleString('ko-KR')} · {jobLabels[j.state]}
                  </option>
                ))}
              </select>
            </label>
          )}
          {state.job && <WatershedResult job={state.job} />}
        </>
      )}
    </aside>
  );
}
