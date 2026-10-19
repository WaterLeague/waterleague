import { topographySource } from '../../spatial/service/spatialSourceService';

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
      '주간은 현재 관측, 재해는 2022.08.08 · 2011.07.27 · 2010.09.21 관측을 사용합니다. 두 모드 모두 서울 25개 구에 관측소를 연결합니다.',
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
    title: '건물·도로·주차장',
    provider: 'OpenStreetMap · Geofabrik · 국토지리정보원',
    description:
      '서울 전역의 건물·도로·보행로·주차장과 설치 후보를 구성합니다. 수치지형도는 성수 건물 경계 대조에 사용합니다.',
    detail:
      '재해 모드도 현재 지도에서 진행합니다. 도로 폭·교량 높이·주차 칸 중 원자료에 없는 값은 표시용으로 구성합니다.',
    datasets: [
      {
        name: 'OpenStreetMap 대한민국 추출본 · south-korea-261016.osm.pbf',
        href: 'https://download.geofabrik.de/asia/south-korea.html',
        detail: '2026-10-16 기준 · 서울 경계·도시 형상·공개 저류 영역·펌프장 건물',
      },
      {
        name: '수치지형도 v2.0(1:1,000) · 성동구 SHP',
        href: topographySource.url,
        detail: `${topographySource.updatedAt} 갱신 · 성수 주변 4개 도엽의 건물 대조`,
      },
    ],
  },
  {
    id: 'terrain',
    title: '지형·토양',
    provider: 'Copernicus · 국립농업과학원 · 브이월드 · EPA',
    description:
      '도시 높낮이를 표시하고 시설 위치별 토성·문헌 추정 투수계수를 연결합니다. 원본 지형은 표시용 90m 격자로 변환합니다.',
    detail:
      '표시 지형은 정밀 배수 지형이 아닙니다. 지하수·구조 하중·매설물 등 현장 시공 조건은 미확인입니다.',
    datasets: [
      {
        name: 'Copernicus DEM GLO-30 · 2021 배포본',
        href: 'https://registry.opendata.aws/copernicus-dem/',
        detail: '30m DSM 원본 → 90m 표시 격자·시설 위치의 지역 경사 참고',
      },
      {
        name: '토양도 · 심토토성(LT_C_ASITDEEPSOIL)',
        href: 'https://www.vworld.kr/dev/v4dv_2ddataguide2_s002.do?svcIde=asitdeepsoil&apiVer=2',
        detail: '공개 토성 분류 · 현장 침투율 실측값은 아님',
      },
      {
        name: 'Storm Water Management Model User’s Manual Version 5.2',
        href: 'https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P10145M6.TXT',
        detail: '토성별 수문 매개변수의 문헌 근거',
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
