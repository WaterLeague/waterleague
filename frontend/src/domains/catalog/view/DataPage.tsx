import { ArrowUpRight, CloudRain, Map, Waves, Users, Layers3, Leaf } from 'lucide-react';
import { useBudget } from '../../budget/controller/useBudget';
import { facilities, won } from '../../game/service/gameService';
import type { FacilityType } from '../../game/entity/game';
import costs from '../../../../../data/costs/lid-reference-v5.json';
import './data-page.css';

const sources = [
  {
    title: '강우·바람',
    icon: CloudRain,
    provider: '기상청 AWS·ASOS',
    description:
      '주간은 현재 관측, 재해는 2022.08.08 · 2011.07.27 · 2010.09.21 관측을 사용합니다. 두 모드 모두 서울 25개 구에 관측소를 연결합니다.',
    detail: '비가 오지 않은 유효 관측은 0mm, 결측·지연은 미확인으로 표시합니다.',
    href: 'https://apihub.kma.go.kr/apiList.do?seqApi=2',
  },
  {
    title: '건물·도로·주차장',
    icon: Map,
    provider: 'OpenStreetMap · 국토지리정보원',
    description:
      '서울 건물·도로·보행로·주차장은 2026년 10월 16일 OSM 자료를 사용합니다. 성수 건물 대조 자료는 2025년 수치지형도입니다.',
    detail:
      '재해 모드도 현재 지도에서 진행합니다. 도로 폭·교량 높이·주차 칸 중 원자료에 없는 값은 표시용으로 구성합니다.',
    href: 'https://www.openstreetmap.org/copyright',
  },
  {
    title: '지형·토양',
    icon: Layers3,
    provider: 'Copernicus · 서울시 공개 공간자료',
    description:
      '도시 높낮이는 Copernicus GLO-30 자료를 90m 격자로 변환해 표시합니다. 시설 계산에는 위치별 공개 토양자료와 문헌 추정값을 사용합니다.',
    detail:
      '표시 지형은 정밀 배수 지형이 아닙니다. 지하수·구조 하중·매설물 등 현장 시공 조건은 미확인입니다.',
    href: 'https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM',
  },
  {
    title: '침수 기록·기존 시설',
    icon: Waves,
    provider: '서울 열린데이터광장 · 공공데이터포털',
    description:
      '공개 침수흔적과 빗물관리시설의 위치·제원을 지도에서 조회합니다. 사용자 설치와 공개 기존 시설을 구분합니다.',
    detail:
      '침수흔적에는 시간별 수심·유속이 없습니다. 기존 시설의 공개 위치는 당시 운영 여부나 실제 부지 경계를 보장하지 않습니다.',
    href: 'https://data.seoul.go.kr/',
  },
  {
    title: '인구·교통',
    icon: Users,
    provider: '서울시 생활인구·실시간 도시데이터',
    description:
      '주간은 주요 121개 장소의 현재 인구·평균 도로 속도를 표시량에 반영합니다. 자료가 없는 곳은 2025년 생활인구 참고값을 사용합니다.',
    detail:
      '재해의 2022년 인구자료는 연결되어 있으며 2010·2011년은 미확보입니다. 움직이는 사람·차량은 실제 개별 위치가 아닙니다.',
    href: 'https://data.seoul.go.kr/dataList/OA-21778/A/1/datasetView.do',
  },
  {
    title: '시설 제원·물 계산',
    icon: Leaf,
    provider: 'EPA SWMM · 공개 설계 문헌',
    description:
      '설치 시설 6종의 단면·침투·저류·배수를 계산합니다. 외부 배수 연결이 확인되지 않은 위치에는 시설에 직접 내리는 비만 유입합니다.',
    detail: '빗물이용조는 설계 초안 단계입니다. 현재 일반 설치·예산·점수에 포함되지 않습니다.',
    href: 'https://www.epa.gov/water-research/storm-water-management-model-swmm',
  },
];

export function DataPage({ accountId }: { accountId: string | null }) {
  const budget = useBudget(0, accountId);
  return (
    <section className="full-page evidence-page data-page" aria-labelledby="data-title">
      <header className="data-page-heading">
        <h1 id="data-title">데이터</h1>
        <p>자료 출처와 게임 적용 범위</p>
      </header>
      <div className="data-source-grid">
        {sources.map(({ title, icon: Icon, provider, description, detail, href }) => (
          <article className="data-source" key={title}>
            <div className="data-source-title">
              <Icon size={20} aria-hidden="true" />
              <h2>{title}</h2>
            </div>
            <p className="data-provider">{provider}</p>
            <p>{description}</p>
            <p className="data-detail">{detail}</p>
            <a href={href} target="_blank" rel="noreferrer">
              {provider.split(' · ')[0]} 출처 <ArrowUpRight size={14} aria-hidden="true" />
            </a>
          </article>
        ))}
      </div>
      <section className="data-costs" aria-labelledby="data-budget-title">
        <h2 id="data-budget-title">예산·설치비</h2>
        <div className="data-budget">
          <span>모드별 개인 예산</span>
          <strong>{budget.value ? won(budget.value.policy.personalLimitKrw) : '—'}</strong>
          <p>주간과 재해는 각각 별도 한도입니다. 재해는 모든 구의 설치비를 합산합니다.</p>
          {budget.value && (
            <a href={budget.value.policy.sourceUrl} target="_blank" rel="noreferrer">
              {budget.value.policy.referenceYear}년 서울시 사업비 참고{' '}
              <ArrowUpRight size={14} aria-hidden="true" />
            </a>
          )}
          {budget.error && <p role="status">예산 정보를 불러오지 못했습니다.</p>}
        </div>
        <p className="data-detail">
          공개 사업비·문헌의 참고 단가로, 실제 개인 지원금이나 현장 견적은 아닙니다.
        </p>
        <div
          className="data-cost-scroll"
          tabIndex={0}
          role="region"
          aria-label="시설별 설치비와 출처"
        >
          <table className="data-cost-table">
            <caption>현재 설치 시설 6종의 면적당 단가</caption>
            <thead>
              <tr>
                <th scope="col">시설</th>
                <th scope="col">원/m²</th>
                <th scope="col">근거</th>
                <th scope="col">포함 범위</th>
              </tr>
            </thead>
            <tbody>
              {(Object.keys(costs.facilities) as FacilityType[]).map((type) => {
                const cost = costs.facilities[type];
                return (
                  <tr key={type}>
                    <th scope="row">{facilities[type].name}</th>
                    <td>{cost.unitCost.toLocaleString('ko-KR')}</td>
                    <td>
                      <a href={cost.sourceUrl} target="_blank" rel="noreferrer">
                        {cost.referenceYear}년{' '}
                        {type === 'GREEN_ROOF'
                          ? '동대문구'
                          : type === 'INFILTRATION_TRENCH'
                            ? 'LH 연구'
                            : '진주 사업계획'}{' '}
                        <ArrowUpRight size={12} aria-hidden="true" />
                      </a>
                    </td>
                    <td>{cost.scope}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="data-detail">
          식생수로는 폭 2m 기준 길이 단가를 면적으로 환산했습니다. 침투도랑은 70m² 시설의 최초
          설치비를 환산했습니다. 시설별 공사 범위가 다르며 유지관리·교체비를 포함한 생애주기비용은
          아직 제공하지 않습니다.
        </p>
      </section>
      <section className="data-calculation" aria-labelledby="data-calculation-title">
        <h2 id="data-calculation-title">점수·침수 계산 범위</h2>
        <dl>
          <div>
            <dt>현재 점수</dt>
            <dd>
              시설 설치 전후의 배출량 차이(m³). 표면 유출·시설 배수·시작과 종료의 저류량 변화를
              반영합니다.
            </dd>
          </div>
          <div>
            <dt>평가 기간</dt>
            <dd>
              주간은 설치 이후 관측, 재해 실험은 설치 시각 이후, 제출 기록은 사건 전체를 계산합니다.
            </dd>
          </div>
          <div>
            <dt>침수 표시</dt>
            <dd>
              자연 하천·과거 침수흔적·계산 결과를 구분합니다. 서울 전역의 실시간 침수 수심·유속은
              현재 제공하지 않습니다.
            </dd>
          </div>
          <div>
            <dt>재현 자료</dt>
            <dd>
              계산에 사용한 강우·배치·시설 제원·비용·엔진 버전과 결과를 저장합니다. 기록에서 권한에
              따라 재현 묶음을 받을 수 있습니다.
            </dd>
          </div>
        </dl>
      </section>
    </section>
  );
}
