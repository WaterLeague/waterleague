type DatasetReference = {
  name: string;
  href: string;
  detail?: string;
};

type DataSource = {
  id: 'weather' | 'geometry' | 'terrain' | 'infrastructure' | 'population' | 'simulation';
  title: string;
  provider: string;
  description: string;
  detail: string;
  datasets: DatasetReference[];
};

const seoulDataset = (id: string, format = 'S') =>
  `https://data.seoul.go.kr/dataList/${id}/${format}/1/datasetView.do`;

export const dataSources: DataSource[] = [
  {
    id: 'weather',
    title: '강우·바람',
    provider: '기상청',
    description:
      '주간은 현재 관측, 재해는 2022.08.08 · 2011.07.27 · 2010.09.21 관측을 사용합니다. 두 모드 모두 서울 25개 구에 관측소를 연결하며 재해는 같은 지점의 7일 선행 기상을 적용합니다.',
    detail: '비가 오지 않은 유효 관측은 0mm, 결측·지연은 미확인으로 표시합니다.',
    datasets: [
      {
        name: '방재기상관측(AWS) 분자료·현재일기',
        href: 'https://apihub.kma.go.kr/apiList.do?seqApi=2&seqApiSub=239',
        detail: '현재·재해 강우와 풍향·풍속, 현재 기상 상태',
      },
      {
        name: '종관기상관측(ASOS) 자료',
        href: 'https://data.kma.go.kr/data/grnd/selectAsosRltmList.do?pgmNo=36&tabNo=2',
        detail: '보관 강우와 선행 기상·증발산 산정의 참고 입력',
      },
    ],
  },
  {
    id: 'geometry',
    title: '건물·도로·설치 경계',
    provider: '국토지리정보원 · 서울특별시 · 서울신용보증재단',
    description:
      '서울 25개 구 수치지형도의 점·선·면 121종 레이어를 지도에 연결합니다. 건물·도로·교량·육교·보도·횡단보도·주차장과 가로수·조명·신호등·시설물을 입체 형상으로 표시합니다. 한강 교량은 공개 자료의 아치·트러스·사장교 구조를 반영하고, 상판·보행로·차량의 높이를 함께 맞춥니다. 설치 후보는 원본 건물명·도로명과 구별 번호를 사용하며 확인되는 주소를 함께 표시합니다.',
    detail:
      '재해도 2026년 갱신 형상에서 진행합니다. 축소도는 원 건물의 대표 경계 상자, 확대 지도는 원형 지물을 사용합니다. 조명·가로등은 원본 위치에만 표시합니다. 도로·보도·주차장의 설치 가능 색상은 같은 원형 후보와 시설별 조건을 따릅니다. 주차장 후보는 기존 후보·건물·교량·수면 등과 겹치는 부분을 제외합니다. 교량 부재 치수·미확인 높이·중심선 도로 폭은 표시용 가정이며 실측 제원이 아닙니다. 차로 수는 원본 속성을 따르며 실제 주차 칸·통행 방향은 임의로 확정하지 않습니다. 1:5,000 레이어는 원래 축척으로 표시합니다. 확보한 도곽 밖 약 37.64㎢는 지도에 상세 지도 미지원 영역으로 표시합니다.',
    datasets: [
      {
        name: '수치지형도 v2.0(1:1,000) · 서울 25개 구 SHP',
        href: 'https://www.data.go.kr/data/15059719/fileData.do',
        detail: '2026-03-07 배포 갱신 · 도엽 제작연도·촬영연도와 구분, 구멍·다중 면 원형 보존',
      },
      {
        name: '서울시 상권분석서비스(영역-자치구)(OA-22161)',
        href: seoulDataset('OA-22161', 'A'),
        detail: '5자리 자치구 코드·소속·집계 경계, 수문 유역 경계로 사용하지 않음',
      },
    ],
  },
  {
    id: 'terrain',
    title: '지형·토양',
    provider: 'Copernicus · EPA',
    description:
      '도시 높낮이는 Copernicus DSM의 90m 표시 격자를 사용합니다. 시설 비교는 공통 Loam 문헌 토양·경사 1%의 참조 시나리오이며 현장 토양·경사를 관측한 값이 아닙니다.',
    detail:
      '표시 지형은 정밀 배수 지형이 아닙니다. 후보와 계산 결과에서 현장 조건별 미확인 상태를 확인할 수 있습니다. 공개 근거로 금지되거나 안전 조건의 충족 확인이 필요한 위치는 배치·계산을 차단하며, 지도 탐색 배치는 실제 시공 승인이 아닙니다.',
    datasets: [
      {
        name: 'Copernicus DEM GLO-30 · 2021 배포본',
        href: 'https://registry.opendata.aws/copernicus-dem/',
        detail:
          '30m DSM 원본 → 90m 표시 격자, 건물·수목을 포함하며 수문 계산 입력으로 사용하지 않음',
      },
      {
        name: 'Storm Water Management Model User’s Manual Version 5.2',
        href: 'https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P10145M6.TXT',
        detail: 'Loam 침투·보수·조도와 시설 단면의 문헌 참조, 현장 시공 적합성은 미확인',
      },
    ],
  },
  {
    id: 'infrastructure',
    title: '침수 기록·기존 시설',
    provider: '서울특별시 · 강서구 · 공공데이터포털',
    description:
      '공개 침수흔적과 빗물관리시설의 위치·제원을 지도에서 조회합니다. 사용자 설치와 공개 기존 시설을 구분합니다.',
    detail:
      '침수흔적에는 시간별 수심·유속이 없습니다. 기존 시설의 공개 위치는 당시 운영 여부나 실제 부지 경계를 보장하지 않습니다.',
    datasets: [
      {
        name: '서울시 침수흔적도(OA-15636)',
        href: seoulDataset('OA-15636', 'F'),
        detail: '2010·2011·2022년 사건의 기록 범위',
      },
      ...[
        ['OA-21179', '빗물펌프장'],
        ['OA-21192', '빗물관리시설'],
        ['OA-21193', '기타 침투시설'],
        ['OA-21194', '침투측구'],
        ['OA-21195', '원형침투통'],
        ['OA-21196', '침투 트렌치'],
        ['OA-21197', '빗물이용시설'],
        ['OA-21199', '정방형침투통'],
      ].map(([id, name]) => ({ name: `서울시 ${name} 공간정보(${id})`, href: seoulDataset(id) })),
      {
        name: '서울특별시 강서구 빗물펌프장 제원(15148889)',
        href: 'https://www.data.go.kr/data/15148889/fileData.do',
        detail: '2025-09-08 기준 공개 제원',
      },
      {
        name: '광진구 빗물펌프장 설비 이력(15021421)',
        href: 'https://www.data.go.kr/data/15021421/fileData.do',
        detail: '2022-01-18 기준 자료의 설치·증설 연도',
      },
    ],
  },
  {
    id: 'population',
    title: '인구·교통',
    provider: '서울특별시',
    description:
      '주간은 주요 121개 장소의 현재 인구·평균 도로 속도를 표시량에 반영합니다. 자료가 없는 곳은 2025년 생활인구 참고값을 사용합니다.',
    detail:
      '재해의 2022년 인구자료는 연결되어 있으며 2010·2011년은 미확보입니다. 움직이는 사람·차량은 실제 개별 위치가 아닙니다.',
    datasets: [
      {
        name: '서울시 실시간 도시데이터(OA-21778)',
        href: seoulDataset('OA-21778', 'A'),
        detail: '121개 장소의 인구 추정·평균 도로 속도',
      },
      {
        name: '서울시 실시간 도시데이터 주요 장소 영역',
        href: seoulDataset('OA-21778', 'F'),
        detail: '2026-04-14 배포 경계 · 관측값을 적용할 장소 범위',
      },
      {
        name: '서울 생활인구 내국인 · 자치구 단위(OA-15439)',
        href: seoulDataset('OA-15439', 'A'),
        detail: '2022년 사건 자료·2025년 요일/시간대 참고값',
      },
    ],
  },
  {
    id: 'simulation',
    title: '시설 제원·물 계산',
    provider: '미국 환경보호청(EPA)',
    description:
      '설치 시설 6종의 단면·침투·저류·배수를 계산합니다. 외부 배수 연결이 확인되지 않은 위치에는 시설에 직접 내리는 비만 유입합니다.',
    detail: '빗물이용조는 설계 초안 단계입니다. 현재 일반 설치·예산·점수에 포함되지 않습니다.',
    datasets: [
      {
        name: 'Storm Water Management Model(SWMM) 5.2.4',
        href: 'https://www.epa.gov/water-research/storm-water-management-model-swmm',
        detail: '물 계산에 사용하는 엔진',
      },
      {
        name: 'SWMM Reference Manual Volume III · Chapter 6',
        href: 'https://nepis.epa.gov/Exe/ZyPDF.cgi/P100P2NY.PDF?Dockey=P100P2NY.PDF',
        detail: '2016년 공개 설계 문헌 · 시설 단면·재료·투수·저류 제원',
      },
    ],
  },
];
