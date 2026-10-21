import type { FacilityType } from '../../game/entity/game';

export const homeFacilities: { type: FacilityType; place: string; action: string }[] = [
  {
    type: 'RAIN_GARDEN',
    place: '허용된 지상 식재 공간',
    action: '낮게 만든 식재 공간에 빗물을 잠시 담고, 토양으로 스며들게 해요.',
  },
  {
    type: 'PERMEABLE_PAVEMENT',
    place: '도로·보도·주차장 후보',
    action: '포장의 틈을 통과한 빗물이 아래층으로 내려가도록 도와요.',
  },
  {
    type: 'GREEN_ROOF',
    place: '건물 지붕',
    action: '지붕 위 흙과 식물이 빗물을 머금어, 흘러나오는 시간을 늦춰요.',
  },
  {
    type: 'BIORETENTION',
    place: '허용된 지상 식재 공간',
    action: '식재토와 아래 쇄석층에 빗물을 담아 땅으로 스며들게 해요.',
  },
  {
    type: 'VEGETATIVE_SWALE',
    place: '허용된 지상 수로 공간',
    action: '풀이 자라는 얕은 수로를 따라 빗물을 흘려보내고 침투시켜요.',
  },
  {
    type: 'INFILTRATION_TRENCH',
    place: '허용된 지상 도랑 공간',
    action: '쇄석 사이의 빈 공간에 빗물을 담고 도랑 바닥으로 침투시켜요.',
  },
  {
    type: 'RAINWATER_CISTERN',
    place: '건물 지붕과 옆 탱크',
    action: '지붕에서 모은 빗물을 탱크에 저장해요. 크기를 고르면 함께 배치돼요.',
  },
];

export const homeModes = [
  {
    id: 'weekly',
    number: '01',
    title: '주간 서울 대항전',
    tag: '실시간 관측 강우',
    href: '/weekly',
    intro: '우리 구에 시설을 놓고, 한 주 동안 빗물에 어떤 변화가 생기는지 확인하세요.',
    rules: [
      '내 소속 구에서 시설 설치',
      '설치 이후 관측 강우의 효과 누적',
      '매주 월요일 새 시즌 시작',
    ],
    link: '우리 구에서 시작하기',
  },
  {
    id: 'disaster',
    number: '02',
    title: '재해 모드',
    tag: '과거 호우 재생',
    href: '/disaster',
    intro: '2010·2011·2022년 호우를 골라 시간을 돌려 보고, 나만의 시설 배치를 실험하세요.',
    rules: [
      '서울 25개 구에서 자유롭게 체험',
      '일시정지·배속·시간 탐색',
      '로그인 후 사건 전체 설계 제출',
    ],
    link: '재해 모드 체험하기',
  },
] as const;
