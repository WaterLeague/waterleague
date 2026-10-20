import { useState } from 'react';
import type { WatershedCatalog } from '../dto/watershedDto';
import type { CisternPlacement } from '../dto/cisternDto';
import type { WatershedState } from '../controller/useWatershed';
import { cisternCatchments } from '../service/cisternDesign';
import { validateCombinedDesign } from '../service/storageDesign';
import { HydraulicPortFields } from './HydraulicPortFields';
import { WatershedDesignReview } from './WatershedDesignReview';
import { WatershedLayout } from './WatershedLayout';
import { physicalAmount as number } from '../../physics/service/physicalValueFormat';
export function CisternDesignForm({
  catalog,
  state,
}: {
  catalog: WatershedCatalog;
  state: WatershedState;
}) {
  const hosts = cisternCatchments(catalog);
  const [draft, setDraft] = useState<CisternPlacement>(() => ({
    id: 'Cistern1',
    catchmentId: hosts[0]?.id ?? '',
    captureAreaM2: NaN,
    areaM2: NaN,
    invertM: NaN,
    depthM: NaN,
    initialDepthM: NaN,
    drainClosed: false,
    drain: { crestM: NaN, diameterM: NaN, dischargeCoefficient: NaN, flapGate: true },
    overflow: { crestM: NaN, diameterM: NaN, dischargeCoefficient: NaN, flapGate: true },
  }));
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const host = hosts.find((c) => c.id === draft.catchmentId);
  if (!host) return <p>이 원본에는 불투수면과 배수 연결이 확인된 집수구역이 없습니다.</p>;
  function add() {
    const used = new Set(
      [...state.drafts, ...state.storageDrafts, ...state.conduitDrafts, ...state.pumpDrafts].map(
        (p) => p.id.toUpperCase()
      )
    );
    let i = 1;
    while (used.has(`CISTERN${i}`)) i++;
    const next = { ...draft, id: `Cistern${i}` };
    const invalid = validateCombinedDesign(
      catalog,
      state.drafts,
      state.storageDrafts,
      state.conduitDrafts,
      state.pumpDrafts,
      next
    );
    setError(invalid);
    setFeedback('');
    if (!invalid) {
      state.setCisternDraft(next);
      setFeedback(`${draft.catchmentId} 이용조 설계 반영`);
    }
  }
  return (
    <section className="watershed-composer" aria-label="빗물이용조 설계">
      <h3>빗물이용조 설계</h3>
      <p>
        집수면의 유출을 밀폐 물통으로 모으고, 연결 관망의 수위에 따라 배수·역류를 계산합니다. 덮개에
        내린 비는 기존 배수 경로로 흐릅니다.
      </p>
      {catalog.layout && (
        <WatershedLayout
          layout={catalog.layout}
          selectedId={draft.catchmentId}
          placements={state.drafts}
          disabled={state.busy}
          onSelect={(id) => {
            if (hosts.some((c) => c.id === id)) setDraft({ ...draft, catchmentId: id });
            else setError('불투수면과 배수 절점이 확인된 집수구역을 선택해 주세요.');
          }}
        />
      )}
      <label>
        집수구역
        <select
          value={draft.catchmentId}
          disabled={state.busy}
          onChange={(e) => setDraft({ ...draft, catchmentId: e.target.value })}
        >
          {hosts.map((c) => (
            <option key={c.id} value={c.id}>
              {c.id} · 배수 절점 {c.outletNodeId}
            </option>
          ))}
        </select>
      </label>
      <p>
        원 면적 {number(host.areaM2)} m² · 불투수 면적 {number(host.imperviousM2)} m² · 보존할 투수
        면적 {number(host.areaM2 - host.imperviousM2)} m². 연결 절점 {host.receiver.id} 높이{' '}
        {number(host.receiver.invertM)}~{number(host.receiver.invertM + host.receiver.maxDepthM)} m.
        원 관망 수직 기준면은 미확인입니다.
      </p>
      <fieldset className="watershed-storage-fields" disabled={state.busy}>
        <legend>신규 시설 설계값</legend>
        <p>
          불투수면 중 집수할 면적과 물통 덮개 면적을 입력합니다. 기존 투수면의 침투는 유지합니다.
          실제 설치 시설의 관측값이 아닌 설계값입니다. 같은 구역의 다른 시설은 이용조 집수와 덮개를
          제외한 불투수면에서만 설치·처리 면적을 배분하며 배수는 원 관망으로 보냅니다.
        </p>
        <div className="watershed-inputs">
          {(
            [
              ['captureAreaM2', '집수 면적 (m²)', 0.01, 1e6, 0.01],
              ['areaM2', '물통 단면·덮개 면적 (m²)', 0.01, 1e6, 0.01],
              ['depthM', '저류 깊이 (m)', 0.001, 100, 0.001],
              ['invertM', '물통 바닥 기준고 (m)', -1000, 10000, 0.001],
              ['initialDepthM', '초기 수심 (m)', 0, 100, 0.001],
            ] as const
          ).map(([key, label, min, max, step]) => (
            <label key={key}>
              {label}
              <input
                type="number"
                min={min}
                max={max}
                step={step}
                value={Number.isFinite(draft[key]) ? draft[key] : ''}
                onChange={(e) => setDraft({ ...draft, [key]: e.target.valueAsNumber })}
              />
            </label>
          ))}
        </div>
        <strong>
          설계 저류 용량{' '}
          {Number.isFinite(draft.areaM2 * draft.depthM) ? number(draft.areaM2 * draft.depthM) : '—'}{' '}
          m³
        </strong>
        <label>
          일반 배출 방식
          <select
            value={draft.drainClosed ? 'closed' : 'gravity'}
            onChange={(e) =>
              setDraft({
                ...draft,
                drainClosed: e.target.value === 'closed',
                drain:
                  e.target.value === 'closed'
                    ? null
                    : {
                        crestM: NaN,
                        diameterM: NaN,
                        dischargeCoefficient: NaN,
                        flapGate: true,
                      },
              })
            }
          >
            <option value="gravity">자연배수 · 관망 수두 반영</option>
            <option value="closed">일반 배출 중지 · 비상 배수만 허용</option>
          </select>
        </label>
        {draft.drainClosed && (
          <p>
            평가 기간 동안 일반 배출과 펌프 사용을 중지하는 설계입니다. 저장된 물을 자동으로
            비우거나 재이용량으로 계산하지 않습니다.
          </p>
        )}
        {draft.drain && (
          <HydraulicPortFields
            label="일반 배수구"
            value={draft.drain}
            onChange={(drain) => setDraft({ ...draft, drain })}
          />
        )}
        <HydraulicPortFields
          label="비상 배수구"
          value={draft.overflow}
          onChange={(overflow) => setDraft({ ...draft, overflow })}
        />
      </fieldset>
      <p className="watershed-warning">
        관망 역압으로 배수가 막히거나 용량을 넘칠 수 있습니다. 홈통 수리·실제 지붕·선행 관측 초기
        수심은 미확보이며, 넘친 물의 지표 연결이 없으면 효과 비교를 보류합니다.
      </p>
      {error && <p role="alert">{error}</p>}
      {feedback && <p role="status">{feedback}</p>}
      <button className="watershed-secondary" disabled={state.busy} onClick={add}>
        {state.cisternDraft ? '이용조 설계 교체' : '설계에 추가'}
      </button>
      <WatershedDesignReview catalog={catalog} state={state} />
    </section>
  );
}
