import { facilityIcons } from '../../facility/view/facilityIcons';
import { X, LockKeyhole } from 'lucide-react';
import type { Account } from '../../account/entity/account';
import type { FacilityType } from '../../game/entity/game';
import type { Budget } from '../../budget/dto/budgetDto';
import { won } from '../../game/service/gameService';
import './watershed.css';
const descriptions = {
  RAIN_GARDEN: '식물과 흙으로 빗물 흡수',
  PERMEABLE_PAVEMENT: '틈새로 빗물이 스며드는 포장',
  GREEN_ROOF: '지붕 위 식물층에 빗물 저장',
  BIORETENTION: '흙과 자갈층에 빗물 저장·침투',
  VEGETATIVE_SWALE: '풀을 심은 수로로 빗물 분산',
  INFILTRATION_TRENCH: '자갈 도랑으로 빗물 침투',
  CISTERN: '지붕 빗물을 건물 옆 탱크에 저장',
  UNDERGROUND_STORAGE: '땅속 탱크에 빗물 저장',
  DETENTION: '넓은 공간에 빗물을 잠시 저장',
  INLET: '도로의 빗물을 배수관으로 전달',
  CONDUIT: '빗물을 모아 배출하는 통로',
  PUMP_STATION: '모인 빗물을 펌프로 배출',
} as const;
const projects = [
  {
    id: 'SEOUL_RAINWATER',
    name: '빗물관리시설 확충',
    items: [
      { id: 'RAIN_GARDEN', name: '빗물정원', Icon: facilityIcons.RAIN_GARDEN, type: 'RAIN_GARDEN' },
      {
        id: 'PERMEABLE_PAVEMENT',
        name: '투수포장',
        Icon: facilityIcons.PERMEABLE_PAVEMENT,
        type: 'PERMEABLE_PAVEMENT',
      },
      { id: 'GREEN_ROOF', name: '녹화지붕', Icon: facilityIcons.GREEN_ROOF, type: 'GREEN_ROOF' },
      {
        id: 'BIORETENTION',
        name: '생물저류시설',
        Icon: facilityIcons.BIORETENTION,
        type: 'BIORETENTION',
      },
      {
        id: 'VEGETATIVE_SWALE',
        name: '식생수로',
        Icon: facilityIcons.VEGETATIVE_SWALE,
        type: 'VEGETATIVE_SWALE',
      },
      {
        id: 'INFILTRATION_TRENCH',
        name: '침투 트렌치',
        Icon: facilityIcons.INFILTRATION_TRENCH,
        type: 'INFILTRATION_TRENCH',
      },
      {
        id: 'CISTERN',
        name: '빗물이용조',
        Icon: facilityIcons.RAINWATER_CISTERN,
        type: 'RAINWATER_CISTERN',
      },
    ],
  },
  {
    id: 'STORAGE',
    name: '빗물저류시설 확충',
    items: [
      {
        id: 'UNDERGROUND_STORAGE',
        name: '지하 저류조',
        Icon: facilityIcons.UNDERGROUND_STORAGE,
        type: null,
      },
      { id: 'DETENTION', name: '저류지·유수지', Icon: facilityIcons.DETENTION, type: null },
    ],
  },
  {
    id: 'DRAINAGE',
    name: '하수관로·빗물받이 정비',
    items: [
      { id: 'INLET', name: '빗물받이', Icon: facilityIcons.INLET, type: null },
      { id: 'CONDUIT', name: '배수관·암거', Icon: facilityIcons.CONDUIT, type: null },
    ],
  },
  {
    id: 'PUMP',
    name: '빗물펌프장 신·증설',
    items: [
      { id: 'PUMP_STATION', name: '빗물펌프장', Icon: facilityIcons.PUMP_STATION, type: null },
    ],
  },
] as const;
export function FacilityExpansionPanel({
  open,
  onClose,
  onMapFacility,
  selectedMapFacility = '',
  budget,
  onConnectedDesign,
  allowedTypes,
}: {
  account: Account | null;
  open: boolean;
  onClose: () => void;
  onMapFacility: (type: FacilityType) => void;
  selectedMapFacility?: FacilityType | '';
  onLogin: () => void;
  budget?: Budget | null;
  onConnectedDesign?: () => void;
  allowedTypes?: FacilityType[];
}) {
  return (
    <aside
      id="facility-install-panel"
      className="shared-inspector watershed-panel"
      aria-label="시설 설치하기"
      hidden={!open}
    >
      <header className="watershed-heading">
        <div>
          <h2>시설 설치하기</h2>
        </div>
        <button className="installation-close" onClick={onClose} aria-label="시설 설치 패널 닫기">
          <X size={18} />
        </button>
      </header>
      {projects.map((project) => {
        const program = budget?.accounting.programs.find((p) => p.id === project.id);
        return (
          <section className="facility-project" key={project.id} aria-label={project.name}>
            <header>
              <h3>{project.name}</h3>
              <div className="facility-project-budget">
                <span>
                  {program
                    ? `사업 예산 ${won(program.limitKrw)}`
                    : budget
                      ? '사업 예산 미설정'
                      : '사업 예산 확인 중'}
                </span>
                {program && <strong>잔액 {won(program.remainingKrw)}</strong>}
              </div>
            </header>
            <div className="watershed-facility-grid">
              {project.items.map(({ id, name, Icon, type }) => {
                return (
                  <button
                    key={id}
                    type="button"
                    disabled={!type || (!!allowedTypes && !allowedTypes.includes(type))}
                    aria-pressed={!!type && selectedMapFacility === type}
                    onClick={() => {
                      if (type) onMapFacility(type);
                    }}
                  >
                    <Icon size={22} />
                    <strong>{name}</strong>
                    <span>{descriptions[id]}</span>
                    {type && allowedTypes && !allowedTypes.includes(type) && (
                      <small>대회 사용 불가</small>
                    )}
                    {!type && (
                      <small>
                        <LockKeyhole size={12} /> 준비 중
                      </small>
                    )}
                  </button>
                );
              })}
            </div>
          </section>
        );
      })}
      <p className="micro-note">같은 사업의 시설은 공동 예산을 사용합니다.</p>
      {onConnectedDesign && (
        <button className="watershed-all-candidates" onClick={onConnectedDesign}>
          서초 연결 유역에서 설계 비교
        </button>
      )}
    </aside>
  );
}
