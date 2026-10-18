import { X, Leaf, Grid2X2, House, Waves, Droplets, Route } from 'lucide-react';
import type { Account } from '../../account/entity/account';
import type { FacilityType } from '../../game/entity/game';
import type { Budget } from '../../budget/dto/budgetDto';
import { won } from '../../game/service/gameService';
import './watershed.css';
const facilities = [
  { id: 'RAIN_GARDEN', name: '빗물정원', Icon: Leaf },
  { id: 'PERMEABLE_PAVEMENT', name: '투수포장', Icon: Grid2X2 },
  { id: 'GREEN_ROOF', name: '녹화지붕', Icon: House },
  { id: 'BIORETENTION', name: '생물저류시설', Icon: Waves },
  { id: 'VEGETATIVE_SWALE', name: '식생수로', Icon: Route },
  { id: 'INFILTRATION_TRENCH', name: '침투 트렌치', Icon: Droplets },
] as const;
const pending = [
  '빗물이용조',
  '지하 저류조',
  '저류지·유수지',
  '빗물받이',
  '배수관·암거',
  '빗물펌프장',
];
export function FacilityExpansionPanel({
  open,
  onClose,
  onMapFacility,
  selectedMapFacility = '',
  onAllCandidates,
  budget,
}: {
  account: Account | null;
  open: boolean;
  onClose: () => void;
  onMapFacility: (type: FacilityType) => void;
  selectedMapFacility?: FacilityType | '';
  onAllCandidates?: () => void;
  onLogin: () => void;
  onCisternPlan?: () => void;
  budget?: Budget | null;
}) {
  return (
    <aside
      id="facility-install-panel"
      className="shared-inspector watershed-panel"
      aria-label="시설 설치하기"
      hidden={!open}
    >
      <header className="watershed-heading">
        <h2>시설 설치하기</h2>
        <button onClick={onClose} aria-label="시설 설치 패널 닫기">
          <X size={18} />
        </button>
      </header>
      <p>시설을 선택하면 설치 가능한 위치만 표시합니다.</p>
      <div className="watershed-facility-grid">
        {facilities.map(({ id, name, Icon }) => {
          const allocation = budget?.accounting.facilities.find(
            (value) => value.facilityType === id
          );
          const program = budget?.accounting.programs.find(
            (value) => value.id === allocation?.programId
          );
          return (
            <button
              key={id}
              aria-pressed={selectedMapFacility === id}
              onClick={() => onMapFacility(id)}
            >
              <Icon size={20} />
              <strong>{name}</strong>
              <span>{program?.name ?? '사업 예산 확인 중'}</span>
              {allocation && <span>사용 가능 {won(allocation.availableKrw)}</span>}
            </button>
          );
        })}
      </div>
      {budget?.accounting.programs.map((program) => (
        <p key={program.id}>
          {program.name} · 공동 한도 {won(program.limitKrw)} · 잔액 {won(program.remainingKrw)}
        </p>
      ))}
      <p className="micro-note">같은 사업에 속한 시설은 하나의 예산을 함께 사용합니다.</p>
      {onAllCandidates && (
        <button className="watershed-all-candidates" onClick={onAllCandidates}>
          시설 선택 해제
        </button>
      )}
      <details className="watershed-pending">
        <summary>설치 연결 중인 시설</summary>
        <p>배수 연결·부지·사업별 예산과 설치 원가를 확인하고 있습니다.</p>
        {pending.map((name) => (
          <div key={name}>
            <strong>{name}</strong>
            <span>설치 연결 중 · 예산 확인 중</span>
          </div>
        ))}
      </details>
    </aside>
  );
}
