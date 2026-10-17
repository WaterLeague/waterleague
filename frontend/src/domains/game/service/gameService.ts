import type { FacilityType, Placement, Lab } from '../entity/game';
export const facilities: Record<
  FacilityType,
  { name: string; short: string; intro: string; description: string; color: string }
> = {
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
};
export function totalCost(lab: Lab, placements: Placement[]) {
  return placements.reduce((n, p) => n + p.areaM2 * lab.model.unitCosts[p.facilityType], 0);
}
const decimalFormat = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 2 });
export const format = {
  format: (value: number) => decimalFormat.format(Math.abs(value) < 0.005 ? 0 : value),
};
export function won(n: number) {
  return new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 }).format(n) + '원';
}
