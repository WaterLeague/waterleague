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
  CircleDot,
  Network,
  Factory,
  LockKeyhole,
} from 'lucide-react';
import type { Account } from '../../account/entity/account';
import type { FacilityType } from '../../game/entity/game';
import type { Budget } from '../../budget/dto/budgetDto';
import { won } from '../../game/service/gameService';
import './watershed.css';
const projects = [
  {
    id: 'SEOUL_RAINWATER',
    name: '빗물관리시설 확충',
    items: [
      { id: 'RAIN_GARDEN', name: '빗물정원', Icon: Leaf, type: 'RAIN_GARDEN' },
      { id: 'PERMEABLE_PAVEMENT', name: '투수포장', Icon: Grid2X2, type: 'PERMEABLE_PAVEMENT' },
      { id: 'GREEN_ROOF', name: '녹화지붕', Icon: House, type: 'GREEN_ROOF' },
      { id: 'BIORETENTION', name: '생물저류시설', Icon: Waves, type: 'BIORETENTION' },
      { id: 'VEGETATIVE_SWALE', name: '식생수로', Icon: Route, type: 'VEGETATIVE_SWALE' },
      {
        id: 'INFILTRATION_TRENCH',
        name: '침투 트렌치',
        Icon: Droplets,
        type: 'INFILTRATION_TRENCH',
      },
      { id: 'CISTERN', name: '빗물이용조', Icon: Container, type: null },
    ],
  },
  {
    id: 'STORAGE',
    name: '빗물저류시설 확충',
    items: [
      { id: 'UNDERGROUND_STORAGE', name: '지하 저류조', Icon: Warehouse, type: null },
      { id: 'DETENTION', name: '저류지·유수지', Icon: Waves, type: null },
    ],
  },
  {
    id: 'DRAINAGE',
    name: '하수관로·빗물받이 정비',
    items: [
      { id: 'INLET', name: '빗물받이', Icon: CircleDot, type: null },
      { id: 'CONDUIT', name: '배수관·암거', Icon: Network, type: null },
    ],
  },
  {
    id: 'PUMP',
    name: '빗물펌프장 신·증설',
    items: [{ id: 'PUMP_STATION', name: '빗물펌프장', Icon: Factory, type: null }],
  },
] as const;
export function FacilityExpansionPanel({
  open,
  onClose,
  onMapFacility,
  selectedMapFacility = '',
  budget,
}: {
  account: Account | null;
  open: boolean;
  onClose: () => void;
  onMapFacility: (type: FacilityType) => void;
  selectedMapFacility?: FacilityType | '';
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
              <span>{program ? `사업 예산 ${won(program.limitKrw)}` : '사업 예산 확인 중'}</span>
            </header>
            <div className="watershed-facility-grid">
              {project.items.map(({ id, name, Icon, type }) => {
                const allocation = budget?.accounting.facilities.find(
                  (f) => f.facilityType === type
                );
                return (
                  <button
                    key={id}
                    disabled={!type}
                    aria-pressed={!!type && selectedMapFacility === type}
                    onClick={() => {
                      if (type) onMapFacility(type);
                    }}
                  >
                    <Icon size={22} />
                    <strong>{name}</strong>
                    {type ? (
                      <span className="facility-availability">
                        {allocation ? (
                          <>
                            <span>잔액</span>
                            <b>{won(allocation.availableKrw)}</b>
                          </>
                        ) : (
                          '예산 확인 중'
                        )}
                      </span>
                    ) : (
                      <span>
                        <LockKeyhole size={12} /> 준비 중
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </section>
        );
      })}
      <p className="micro-note">같은 사업의 시설은 공동 예산을 사용합니다.</p>
    </aside>
  );
}
