import { PumpDesignForm } from './PumpDesignForm';
import { ConduitDesignForm } from './ConduitDesignForm';
import { useState } from 'react';
import {
  X,
  Leaf,
  Grid2X2,
  House,
  Waves,
  Droplets,
  Route,
  Container,
  Warehouse,
  Fence,
  CircleDot,
  Network,
  Factory,
} from 'lucide-react';
import type { Account } from '../../account/entity/account';
import type { FacilityType } from '../../game/entity/game';
import type { NetworkFacility } from '../dto/watershedDto';
import { useWatershed } from '../controller/useWatershed';
import { StorageDesignForm } from './StorageDesignForm';
import { NetworkDesignForm } from './NetworkDesignForm';
import { jobLabels, WatershedResult } from './WatershedResult';
import './watershed.css';
const mapFacilities = [
  { id: 'RAIN_GARDEN', name: '빗물정원', Icon: Leaf },
  { id: 'PERMEABLE_PAVEMENT', name: '투수포장', Icon: Grid2X2 },
  { id: 'GREEN_ROOF', name: '녹화지붕', Icon: House },
  { id: 'BIORETENTION', name: '생물저류시설', Icon: Waves },
] as const;
const networkFacilities = [
  { id: 'BIORETENTION', name: '생물저류시설', Icon: Waves },
  { id: 'INFILTRATION_TRENCH', name: '침투 트렌치', Icon: Droplets },
  { id: 'VEGETATIVE_SWALE', name: '식생수로', Icon: Route },
  { id: 'RAINWATER_CISTERN', name: '빗물이용조', Icon: Container },
  { id: 'UNDERGROUND_STORAGE', name: '지하 저류조', Icon: Warehouse },
  { id: 'CONDUIT', name: '배수관·암거', Icon: Network },
  { id: 'PUMP_STATION', name: '빗물펌프장', Icon: Factory },
] as const;
const pendingFacilities = [
  { name: '저류지·유수지', Icon: Fence, reason: '수위별 저류 용량·월류 구조·부지·원가 연결 필요' },
  {
    name: '빗물받이',
    Icon: CircleDot,
    reason: '유입부 단면·기준고·관망과 지표의 같은 좌표계 연결 필요',
  },
];
export function FacilityExpansionPanel({
  account,
  open,
  onClose,
  onMapFacility,
  selectedMapFacility = '',
  onAllCandidates,
  onLogin,
}: {
  account: Account | null;
  open: boolean;
  onClose: () => void;
  onMapFacility: (type: FacilityType) => void;
  selectedMapFacility?: FacilityType | '';
  onAllCandidates?: () => void;
  onLogin: () => void;
}) {
  const [type, setType] = useState<
    NetworkFacility | 'UNDERGROUND_STORAGE' | 'CONDUIT' | 'PUMP_STATION' | null
  >(null);
  const state = useWatershed(account, open);
  return (
    <aside
      id="facility-install-panel"
      className="shared-inspector watershed-panel"
      aria-label="시설 설치하기"
      hidden={!open}
    >
      <header className="watershed-heading">
        <div>
          <span>WATER LEAGUE / 시설</span>
          <h2>시설 설치하기</h2>
        </div>
        <button onClick={onClose} aria-label="시설 설치 패널 닫기">
          <X size={18} />
        </button>
      </header>
      <p>설치할 시설을 고른 뒤 지도에서 위치를 선택하세요.</p>
      <h3>
        지도에 설치 <small>4종</small>
      </h3>
      <div className="watershed-facility-grid">
        {mapFacilities.map(({ id, name, Icon }) => (
          <button
            key={id}
            aria-pressed={selectedMapFacility === id}
            onClick={() => onMapFacility(id)}
          >
            <Icon size={20} />
            <strong>{name}</strong>
            <span>지도 위치 선택</span>
          </button>
        ))}
      </div>
      {onAllCandidates && (
        <button className="watershed-all-candidates" onClick={onAllCandidates}>
          전체 시설의 설치 후보 보기
        </button>
      )}
      <h3>
        연결 유역 비교 <small>생물저류 포함 7종</small>
      </h3>
      <p>
        생물저류시설은 공개 토성 후보에서 지도 설치가 가능합니다. 나머지 6종은 관망 계산에서 사용할
        수 있으며, 지도 설치 연결을 진행 중입니다.
      </p>
      <div className="watershed-facility-grid">
        {networkFacilities.map(({ id, name, Icon }) => (
          <button key={id} aria-pressed={type === id} onClick={() => setType(id)}>
            <Icon size={20} />
            <strong>{name}</strong>
            <span>관망 설계·계산</span>
          </button>
        ))}
      </div>
      {type && !account && (
        <div className="watershed-access">
          <p>회원으로 로그인하면 공개 관망에서 시설을 설계하고 계산할 수 있습니다.</p>
          <button className="watershed-submit" onClick={onLogin}>
            로그인하고 설계
          </button>
        </div>
      )}
      {type && account && !state.allowed && (
        <p className="watershed-warning">승인된 회원 계정으로 관망 설계를 사용할 수 있습니다.</p>
      )}
      {state.allowed && (
        <>
          {state.loading && !state.catalog && (
            <p role="status">공개 관망과 내 계산 기록 조회 중…</p>
          )}
          {state.error && (
            <p role="alert" className="watershed-warning">
              {state.error}
              <button disabled={state.loading} onClick={state.retry}>
                다시 조회
              </button>
            </p>
          )}
          {state.catalog &&
            type &&
            (type === 'PUMP_STATION' ? (
              <PumpDesignForm catalog={state.catalog} state={state} />
            ) : type === 'CONDUIT' ? (
              <ConduitDesignForm catalog={state.catalog} state={state} />
            ) : type === 'UNDERGROUND_STORAGE' ? (
              <StorageDesignForm catalog={state.catalog} state={state} />
            ) : (
              <NetworkDesignForm type={type} catalog={state.catalog} state={state} />
            ))}
          {state.jobs.length > 0 && (
            <label className="watershed-history">
              내 최근 관망 계산
              <select value={state.job?.id ?? ''} onChange={(e) => state.selectJob(e.target.value)}>
                {state.jobs.map((job) => (
                  <option key={job.id} value={job.id}>
                    {new Date(job.createdAt).toLocaleString('ko-KR')} ·{' '}
                    {job.design.placements.length +
                      (job.design.storage?.placements.length ?? 0) +
                      (job.design.conduits?.placements.length ?? 0) +
                      (job.design.pumps?.placements.length ?? 0)}
                    곳 · {jobLabels[job.state]}
                  </option>
                ))}
              </select>
            </label>
          )}
          {state.job && <WatershedResult job={state.job} />}
          {state.catalog && (
            <details className="watershed-source">
              <summary>{state.catalog.catalog.title} · 출처와 적용 범위</summary>
              <p>
                집수구역 {state.catalog.catalog.catchments.length}개 · 공개 연구 모형이며 공식 시설
                대장이 아닙니다.
              </p>
              <a href={state.catalog.catalog.sourceUrl} target="_blank" rel="noreferrer">
                공개 원본 · {state.catalog.catalog.attribution.year}
              </a>
              <p>{state.catalog.catalog.attribution.authors.join(', ')}</p>
              <a href={state.catalog.catalog.licence.url} target="_blank" rel="noreferrer">
                {state.catalog.catalog.licence.short_name}
              </a>
              <ul>
                {state.catalog.catalog.limitations.map((text, i) => (
                  <li key={i}>{text}</li>
                ))}
              </ul>
              <p>
                원본 관망에서 수치 설정과 시설 배치를 변경한 비교입니다. 좌표계가 확인되지 않아
                지도에 관로 위치를 추정해 표시하지 않습니다.
              </p>
            </details>
          )}
        </>
      )}
      <details className="watershed-pending">
        <summary>
          연결 준비 중인 시설 <span>2종</span>
        </summary>
        <p>아래 시설은 아직 설치하거나 이 화면에서 계산할 수 없습니다.</p>
        {pendingFacilities.map(({ name, Icon, reason }) => (
          <div key={name}>
            <Icon size={18} />
            <strong>{name}</strong>
            <p>{reason}</p>
          </div>
        ))}
      </details>
    </aside>
  );
}
