import { GameDataError } from '../exception/GameDataError';
import type { FacilityType, Placement, Lab, UnitCosts } from '../entity/game';
export const facilities: Record<
  FacilityType,
  { name: string; short: string; intro: string; description: string; color: string }
> = {
  RAINWATER_CISTERN: {
    name: '빗물이용조',
    short: '이용조',
    color: '#548eae',
    intro: '지붕의 빗물을 모아 저장하고 천천히 배출하는 시설.',
    description:
      '건물의 빗물을 지붕에서 모아 건물 옆 탱크에 저장합니다. 크기를 고르고 바로 설치하세요.',
  },
  RAIN_GARDEN: {
    name: '빗물정원',
    short: '정원',
    intro: '빗물을 담아 땅으로 스며들게 하는 식재 공간.',
    description: '식재 토양과 바닥 침투로 빗물 분산. 지하수·지장물 확인 필요.',
    color: '#6f9474',
  },
  PERMEABLE_PAVEMENT: {
    name: '투수포장',
    short: '포장',
    intro: '빗물이 틈을 통과해 아래층으로 내려가는 포장.',
    description: '포장층 아래로 빗물 통과. 통행 하중·막힘·기층 검토 필요.',
    color: '#7f9ba7',
  },
  GREEN_ROOF: {
    name: '녹화지붕',
    short: '지붕',
    intro: '지붕의 흙·식물층에 빗물을 머금게 하는 시설.',
    description: '지붕에서 빗물 저장과 방류 지연. 구조 하중·방수 확인 필요.',
    color: '#b3a464',
  },
  VEGETATIVE_SWALE: {
    name: '식생수로',
    short: '수로',
    intro: '식생을 심은 얕은 수로에서 빗물을 흘리고 침투시키는 시설.',
    description: '폭 2m 직선 수로 설계. 공개 토성·지역 경사 후보에서 자체 강우만 처리.',
    color: '#68966b',
  },
  INFILTRATION_TRENCH: {
    name: '침투 트렌치',
    short: '침투도랑',
    intro: '쇄석 공극에 빗물을 담아 바닥으로 침투시키는 도랑.',
    description: '폭 1m 개방 쇄석 도랑 설계. 지하 유공관·외부 집수 연결 없는 직접 강우 계산.',
    color: '#8f9cb5',
  },
  BIORETENTION: {
    name: '생물저류시설',
    short: '생물저류',
    intro: '식재토 아래 쇄석층에 빗물을 저장하고 땅으로 침투시키는 시설.',
    description: '식재토·쇄석 저류층의 침투형 설계. 공개 토성 후보에서 자체 강우만 처리.',
    color: '#4f8e8a',
  },
};
export function unitCost(costs: UnitCosts, type: FacilityType) {
  const value = costs[type];
  if (value === undefined || !Number.isFinite(value) || value <= 0) throw new GameDataError();
  return value;
}
export function totalCost(lab: Lab, placements: Placement[]) {
  return placements.reduce(
    (n, p) => n + p.areaM2 * unitCost(lab.model.unitCosts, p.facilityType),
    0
  );
}
const decimalFormat = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 2 });
export const format = {
  format: (value: number) => decimalFormat.format(Math.abs(value) < 0.005 ? 0 : value),
};
export function won(n: number) {
  return new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 }).format(n) + '원';
}
