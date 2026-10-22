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
    intro:
      '우리 구에 시설을 설치하고 실제 관측 강우로 계산되는 효과를 쌓으세요. 개인과 구의 누적 점수를 실시간 랭킹에서 함께 비교할 수 있어요.',
    rules: [
      '내 소속 구에서 시설 설치',
      '설치 이후 관측 강우의 효과 누적',
      '개인·구별 랭킹 갱신, 매주 월요일 새 시즌',
    ],
    image: {
      src: '/home/game/weekly-rankings.png',
      alt: '서울 전체 지도에 구별 점수와 순위가 표시되고 1위 도봉구가 강조된 주간 서울 대항전 화면',
      width: 2032,
      height: 1322,
      caption: '구별 누적 점수와 실시간 랭킹 · 게임 화면',
    },
    link: '우리 구에서 시작하기',
  },
  {
    id: 'disaster',
    number: '02',
    title: '재해 모드',
    tag: '과거 호우 재생',
    href: '/disaster',
    intro:
      '2010·2011·2022년 실제 호우의 관측 강우와 침수 기록을 살펴보고, 그 비가 다시 내린다면 내 시설 배치가 어떤 차이를 만드는지 시뮬레이션으로 실험하세요.',
    rules: [
      '서울 25개 구에서 자유롭게 체험',
      '일시정지·배속·시간 탐색',
      '로그인 후 사건 전체 설계 제출',
    ],
    image: {
      src: '/home/game/disaster-replay.png',
      alt: '과거 호우의 침수 기록을 표시한 영등포구 지도에서 투수포장의 면적과 비용을 조절하는 재해 모드 화면',
      width: 2134,
      height: 1286,
      caption: '과거 호우 기록을 살펴보며 시설 배치 실험 · 게임 화면',
    },
    link: '재해 모드 체험하기',
  },
] as const;
