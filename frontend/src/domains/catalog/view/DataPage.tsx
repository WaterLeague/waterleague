import { ArrowUpRight, CloudRain, Map, Waves, Users, Layers3, Leaf } from 'lucide-react';
import { useBudget } from '../../budget/controller/useBudget';
import { facilities, won } from '../../game/service/gameService';
import type { FacilityType } from '../../game/entity/game';
import costs from '../../../../../data/costs/lid-reference-v5.json';
import maintenance from '../../../../../data/facilities/maintenance-reference-v1.json';
import suitability from '../../../../../backend/src/main/resources/facilities/site-suitability-v1.json';
import { dataSources } from '../service/dataSourceService';
import './data-page.css';

const sourceIcons = {
  weather: CloudRain,
  geometry: Map,
  terrain: Layers3,
  infrastructure: Waves,
  population: Users,
  simulation: Leaf,
};

const suitabilityLabels: Record<string, { label: string; condition: string }> = {
  PROHIBITED: { label: '금지', condition: '공개 근거로 금지 조건 확인' },
  CONDITIONAL: { label: '조건부', condition: '명시된 안전 조건의 충족 근거 필요' },
  UNKNOWN: { label: '미확인', condition: '금지·조건부는 없으나 현장 근거가 빠짐' },
  ELIGIBLE: { label: '허용', condition: '해당 위치의 모든 필수 조건에 허용 근거 확보' },
};

export function DataPage({ accountId }: { accountId: string | null }) {
  const budget = useBudget(0, accountId);
  return (
    <section className="full-page evidence-page data-page" aria-labelledby="data-title">
      <header className="data-page-heading">
        <h1 id="data-title">데이터</h1>
        <p>사용 데이터·문헌과 게임 적용 범위</p>
      </header>
      <div className="data-source-grid">
        {dataSources.map(({ id, title, provider, description, detail, datasets }) => {
          const Icon = sourceIcons[id];
          return (
            <article className="data-source" key={id}>
              <div className="data-source-title">
                <Icon size={20} aria-hidden="true" />
                <h2>{title}</h2>
              </div>
              <p className="data-provider">{provider}</p>
              <p>{description}</p>
              <p className="data-detail">{detail}</p>
              <h3>사용 데이터·문헌</h3>
              <ul className="data-dataset-list">
                {datasets.map((dataset) => (
                  <li key={dataset.name}>
                    <a href={dataset.href} target="_blank" rel="noreferrer">
                      <span>{dataset.name}</span>
                      <ArrowUpRight size={13} aria-hidden="true" />
                    </a>
                    {dataset.detail && <p>{dataset.detail}</p>}
                  </li>
                ))}
              </ul>
            </article>
          );
        })}
      </div>
      <section className="data-costs" aria-labelledby="data-budget-title">
        <h2 id="data-budget-title">예산·설치비</h2>
        <div className="data-budget">
          <span>모드별 개인 예산</span>
          <strong>{budget.value ? won(budget.value.policy.personalLimitKrw) : '—'}</strong>
          <p>주간과 재해는 각각 별도 한도입니다. 재해는 모든 구의 설치비를 합산합니다.</p>
          {budget.value && (
            <a href={budget.value.policy.sourceUrl} target="_blank" rel="noreferrer">
              {budget.value.policy.sourceTitle} <ArrowUpRight size={14} aria-hidden="true" />
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
                        {cost.sourceTitle} · {cost.referenceYear}년{' '}
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
          설치비를 환산했습니다. 시설별 공사 범위가 다르며 전체 생애주기비용은 미산정입니다.
          빗물이용조 견적에는 문헌의 기간·할인 가정에 따른 부분 현재가치를 별도로 제공합니다. 미확정
          교체·처분비·잔존가치를 0원으로 채우거나 설치 예산·물리 점수에 합산하지 않습니다.
        </p>
        <details className="data-maintenance-reference">
          <summary>유지관리·현장 적합성의 근거와 판정 기준</summary>
          <p>
            아래는 공개 문헌의 점검 참고 기준입니다. 현재 지도 후보의 점검·정비 이력은 미확인이며,
            관리 상태·실현성 점수와 상·중·하 등급은 산정하지 않습니다.
          </p>
          <div
            className="data-cost-scroll"
            tabIndex={0}
            role="region"
            aria-label="시설별 관리 근거"
          >
            <table className="data-cost-table data-reference-table">
              <caption>시설별 관리 항목과 문헌 권고 주기</caption>
              <thead>
                <tr>
                  <th scope="col">시설</th>
                  <th scope="col">확인 항목</th>
                  <th scope="col">문헌 주기·조사 신호</th>
                  <th scope="col">출처</th>
                </tr>
              </thead>
              <tbody>
                {maintenance.facilities.map((row) => {
                  const source =
                    maintenance.sources[row.source as keyof typeof maintenance.sources];
                  return (
                    <tr key={row.type}>
                      <th scope="row">{row.label}</th>
                      <td>{row.checks}</td>
                      <td>
                        {row.frequency}
                        {row.limitation && <p className="data-detail">{row.limitation}</p>}
                      </td>
                      <td>
                        <a href={source.url} target="_blank" rel="noreferrer">
                          {source.publisher} · {source.year}년
                          <ArrowUpRight size={12} aria-hidden="true" />
                        </a>
                        <p className="data-detail">{row.reference}</p>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <h3>관리 상태를 판단할 수 있는 근거</h3>
          <dl className="data-assessment-rules">
            {maintenance.decisionRules.map((rule) => (
              <div key={rule.id}>
                <dt>{rule.label}</dt>
                <dd>
                  {rule.condition}. {rule.result}
                </dd>
              </div>
            ))}
          </dl>
          <p className="data-detail">
            시설·위치·규격, 점검·정비 시각, 측정 방법·단위·결측, 관리 주체·접근과 비용 근거를 함께
            확인해야 합니다. 비교 배점·등급 경계가 검증되기 전에는 점검 기록이 있어도 점수를 만들지
            않습니다. 문헌 주기를 자동 노후화·청소 효과·관리비로 환산하지 않습니다.
          </p>
          <div
            className="data-cost-scroll"
            tabIndex={0}
            role="region"
            aria-label="현장 적합성 판정표"
          >
            <table className="data-cost-table data-reference-table">
              <caption>현재 서버의 현장 적합성 판정 · 위쪽 상태 우선</caption>
              <thead>
                <tr>
                  <th scope="col">상태</th>
                  <th scope="col">근거 조건</th>
                  <th scope="col">게임 배치·계산</th>
                </tr>
              </thead>
              <tbody>
                {suitability.priority.map((status) => (
                  <tr key={status}>
                    <th scope="row">{suitabilityLabels[status].label}</th>
                    <td>{suitabilityLabels[status].condition}</td>
                    <td>
                      {suitability.explorationAllowed.includes(status) ? '탐색 허용' : '차단'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="data-detail">
            토양·경사·지하수·지장물·교통 하중 또는 옥상 구조·방수·배수의 해당 조건을 판정합니다. 각
            조건에 사유와 공개 출처·버전을 보존하며 모든 상태에서 현장 시공 승인은 별도입니다.
            관리·실현성 판단을 체적 차이 순위에 합산하지 않습니다.
          </p>
        </details>
      </section>
      <section className="data-calculation" aria-labelledby="data-calculation-title">
        <h2 id="data-calculation-title">점수·침수 계산 범위</h2>
        <dl>
          <div>
            <dt>현재 점수</dt>
            <dd>
              시설 설치 전후의 평가체적 차이(m³). 표면 유출·시설 배수·시작과 종료의 저류량 변화를
              반영합니다. 계산 전 기록은 미계산으로 표시하며 실제 0·음수와 구분합니다. 설치 전후
              개선율은 보조값이고 순위에는 사용하지 않습니다. 평가 규칙·계산 조건을 사전에 고정하며
              같은 저장값은 공동 순위입니다. 조건이 다른 재해 기록은 별도로 비교하고, 주간에 다른
              조건이 섞이면 합산·순위를 보류합니다.
            </dd>
          </div>
          <div>
            <dt>평가 기간</dt>
            <dd>
              주간은 서버가 기록한 설치 초부터 관측이 확보된 시각까지 누적합니다. 재해 실험은 설치
              시각 이후, 제출 기록은 사건 전체를 계산합니다. 앞선 7일의 관측은 초기 수분·저류 상태를
              계산하는 데 사용하며 점수 기간에서 제외합니다. 평가 구간에 비가 없어도 증발·저류
              상태의 변화로 평가체적 차이가 생길 수 있습니다.
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
              계산에 사용한 강우·배치·시설 제원·비용·엔진 버전과 결과를 저장합니다. 새 계산은 원형
              표면의 면적 배분과 연결 근거도 보관합니다. 배수 관망·지표 침수 격자가 연결되지 않은
              위치는 미연결로 남깁니다. 기록에서 권한에 따라 재현 묶음을 받을 수 있습니다.
            </dd>
          </div>
        </dl>
      </section>
    </section>
  );
}
