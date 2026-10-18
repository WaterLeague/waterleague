import { useRef, useState } from 'react';
import type { NetworkFacility, NetworkPlacement, WatershedCatalog } from '../dto/watershedDto';
import { networkNames } from '../service/watershedDesign';
import { physicalAmount as number } from '../../physics/service/physicalValueFormat';
import type { WatershedState } from '../controller/useWatershed';
import { validateCombinedDesign } from '../service/storageDesign';
import { WatershedDesignReview } from './WatershedDesignReview';
import { WatershedLayout } from './WatershedLayout';
const areaAmount = (value: number) => value.toLocaleString('ko-KR', { maximumFractionDigits: 2 });
const parameterLabels: Record<string, string> = {
  surfaceDepthMm: '표면 저류 깊이 (mm)',
  vegetationFraction: '식생 체적 비율',
  soilDepthMm: '토양층 깊이 (mm)',
  storageDepthMm: '저류층 깊이 (mm)',
  storagePorosity: '저류층 공극률',
  nativeSeepageMmH: '하부 침투율 가정 (mm/h)',
  bottomWidthM: '바닥 폭 (m)',
  sideSlope: '사면 수평/수직 비',
  slopePercent: '종단 경사 가정 (%)',
  roughness: 'Manning 조도',
  diameterMm: '배수구 구경 (mm)',
  dischargeCoefficient: '방류계수',
  offsetMm: '배수구 높이 (mm)',
  delayHours: '배수 지연 (시간)',
};
function Parameters({ values }: { values: Record<string, unknown> }) {
  return (
    <dl className="watershed-parameters">
      {Object.entries(values).flatMap(([key, value]) => {
        if (key === 'drain')
          return [
            <div key={key}>
              <dt>하부 배수</dt>
              <dd>
                {value && typeof value === 'object' ? (
                  <Parameters values={value as Record<string, unknown>} />
                ) : (
                  '배수관 없음'
                )}
              </dd>
            </div>,
          ];
        if (typeof value !== 'number' || !parameterLabels[key]) return [];
        return [
          <div key={key}>
            <dt>{parameterLabels[key]}</dt>
            <dd>{number(value)}</dd>
          </div>,
        ];
      })}
    </dl>
  );
}
export function NetworkDesignForm({
  type,
  catalog,
  state,
}: {
  type: NetworkFacility;
  catalog: WatershedCatalog;
  state: WatershedState;
}) {
  const [catchmentId, setCatchment] = useState(catalog.catalog.catchments[0].id);
  const [area, setArea] = useState('');
  const [treated, setTreated] = useState('');
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const sequence = useRef(0);
  const catchment = catalog.catalog.catchments.find((c) => c.id === catchmentId)!;
  const occupied = state.drafts
    .filter((p) => p.catchmentId === catchmentId)
    .reduce((sum, p) => sum + p.areaM2 + p.treatedImperviousM2, 0);
  const template = catalog.catalog.templates[type];
  function add() {
    setFeedback('');
    if (!area.trim() || !treated.trim()) {
      setError(
        '시설 면적과 추가 처리 면적을 모두 입력해 주세요. 추가 유입이 없으면 0을 입력합니다.'
      );
      return;
    }
    const placement: NetworkPlacement = {
      id: `F${sequence.current + 1}`,
      facilityType: type,
      catchmentId,
      areaM2: Number(area),
      treatedImperviousM2: Number(treated),
    };
    while (
      [...state.drafts, ...state.storageDrafts, ...state.conduitDrafts].some(
        (p) => p.id === placement.id
      )
    )
      placement.id = `F${++sequence.current + 1}`;
    const next = [...state.drafts, placement];
    const invalid = validateCombinedDesign(catalog, next, state.storageDrafts, state.conduitDrafts);
    if (invalid) {
      setError(invalid);
      return;
    }
    sequence.current++;
    state.setDrafts(next);
    setError('');
    setFeedback(`${catchmentId}에 ${networkNames[type]} ${number(placement.areaM2)} m² 추가`);
  }
  return (
    <section className="watershed-composer" aria-label="관망 시설 설계">
      <h3>{networkNames[type]} 설계</h3>
      <p>
        공개 연구 관망의 집수구역에 연결합니다. 면적은 사용자가 정하는 설계값이며 현장 시공 가능
        면적은 미확인입니다.
      </p>
      {catalog.layout && (
        <WatershedLayout
          layout={catalog.layout}
          selectedId={catchmentId}
          placements={state.drafts}
          disabled={state.busy}
          onSelect={(id) => {
            setCatchment(id);
            setError('');
            setFeedback('');
          }}
        />
      )}
      <label>
        집수구역
        <select
          value={catchmentId}
          onChange={(e) => {
            setCatchment(e.target.value);
            setError('');
          }}
          disabled={state.busy}
        >
          {catalog.catalog.catchments.map((c) => (
            <option key={c.id} value={c.id}>
              {c.id} · 배수 절점 {c.outletNodeId}
            </option>
          ))}
        </select>
      </label>
      <p className="watershed-capacity">
        공개 불투수 면적 {areaAmount(catchment.imperviousM2)} m²
        <br />이 설계의 잔여 면적{' '}
        {areaAmount(Math.floor(Math.max(0, catchment.imperviousM2 - occupied) * 100) / 100)} m²
      </p>
      <div className="watershed-inputs">
        <label>
          시설 면적 (m²)
          <input
            type="number"
            min="0.01"
            max="1000000"
            step="0.01"
            value={area}
            onChange={(e) => setArea(e.target.value)}
            disabled={state.busy}
          />
        </label>
        <label>
          추가 처리 면적 (m²)
          <input
            type="number"
            min="0"
            max="1000000"
            step="0.01"
            value={treated}
            onChange={(e) => setTreated(e.target.value)}
            disabled={state.busy}
          />
        </label>
      </div>
      <p>
        시설 면적만큼 기존 불투수면을 대체하고, 추가 처리 면적의 빗물을 시설로 보냅니다. 같은 면적을
        여러 시설에 중복 배분할 수 없습니다.
      </p>
      <details>
        <summary>적용 단면·재료·초기 조건</summary>
        <p>EPA 문헌 참고 제원 · 현장 측정값 아님</p>
        <Parameters values={template.parameters} />
        <p>
          {type === 'VEGETATIVE_SWALE'
            ? '식생수로에는 초기 포화율을 적용하지 않습니다.'
            : `초기 포화율 ${template.initialSaturationPercent}% · 설계 가정`}
        </p>
        <p>이 공개 관망 비교에는 선행 관측 기반 초기화가 아직 연결되지 않았습니다.</p>
      </details>
      {error && (
        <p role="alert" className="watershed-warning">
          {error}
        </p>
      )}
      {feedback && <p role="status">{feedback}</p>}
      <button
        type="button"
        className="watershed-secondary"
        disabled={
          state.busy ||
          state.drafts.length + state.storageDrafts.length + state.conduitDrafts.length >= 20
        }
        onClick={add}
      >
        설계에 추가
      </button>
      <WatershedDesignReview catalog={catalog} state={state} />
    </section>
  );
}
