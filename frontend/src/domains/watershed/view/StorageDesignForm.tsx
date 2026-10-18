import { useState } from 'react';
import type { WatershedState } from '../controller/useWatershed';
import type { WatershedCatalog } from '../dto/watershedDto';
import type { StoragePlacement, StoragePort } from '../dto/storageDto';
import { validateCombinedDesign } from '../service/storageDesign';
import { WatershedDesignReview } from './WatershedDesignReview';
import { WatershedLayout } from './WatershedLayout';
import { physicalAmount as number } from '../../physics/service/physicalValueFormat';

const portNames = { inlet: '유입구', drain: '일반 배수구', overflow: '비상 배수구' };
function initialDesign(catalog: WatershedCatalog, id: string): StoragePlacement {
  const c = catalog.storageCatalog!.connections.find((c) => c.id === id)!;
  const floor = Math.max(c.inlet.invertM, c.receiver.invertM);
  const top = Math.min(
    c.inlet.invertM + c.inlet.maxDepthM,
    c.receiver.invertM + c.receiver.maxDepthM
  );
  const round = (n: number) => Math.round(n * 1000) / 1000;
  const diameter = Math.floor(Math.min(0.2, (top - floor) / 4) * 1000) / 1000;
  const port = (crestM: number, diameterM: number): StoragePort => ({
    crestM: round(crestM),
    diameterM,
    dischargeCoefficient: 0.65,
    flapGate: false,
  });
  return {
    id: 'Tank1',
    connectionId: id,
    areaM2: 100,
    invertM: c.receiver.invertM,
    depthM: round(top - c.receiver.invertM),
    initialDepthM: 0,
    inlet: port(floor, diameter),
    drain: port(c.receiver.invertM, Math.min(0.03, diameter)),
    overflow: port(top - diameter, diameter),
  };
}
export function StorageDesignForm({
  catalog,
  state,
}: {
  catalog: WatershedCatalog;
  state: WatershedState;
}) {
  const connections = catalog.storageCatalog?.connections;
  if (!connections?.length) return <p>이 관망 버전에는 저류조 연결 자료가 없습니다.</p>;
  return <Composer key={catalog.storageCatalogHash} catalog={catalog} state={state} />;
}
function Composer({ catalog, state }: { catalog: WatershedCatalog; state: WatershedState }) {
  const connections = catalog.storageCatalog!.connections;
  const [draft, setDraft] = useState(() => initialDesign(catalog, connections[0].id));
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const connection = connections.find((c) => c.id === draft.connectionId)!;
  function select(id: string) {
    setDraft(initialDesign(catalog, id));
    setError('');
    setFeedback('');
  }
  function add() {
    let i = 1;
    const used = new Set(
      [...state.drafts, ...state.storageDrafts, ...state.conduitDrafts, ...state.pumpDrafts].map(
        (p) => p.id.toUpperCase()
      )
    );
    while (used.has(`TANK${i}`)) i++;
    const next = [...state.storageDrafts, { ...draft, id: `Tank${i}` }];
    const invalid = validateCombinedDesign(
      catalog,
      state.drafts,
      next,
      state.conduitDrafts,
      state.pumpDrafts
    );
    setError(invalid);
    setFeedback('');
    if (!invalid) {
      state.setStorageDrafts(next);
      setFeedback(
        `${connection.id} 연결에 지하 저류조 ${number(draft.areaM2 * draft.depthM)} m³ 추가`
      );
    }
  }
  return (
    <section className="watershed-composer" aria-label="지하 저류조 설계">
      <h3>지하 저류조 설계</h3>
      <p>
        기존 관로의 두 절점 사이에 덮개·차수 저류조를 추가합니다. 기존 관로는 유지되며, 세 개구부의
        수두 차이로 유입·배수·역류를 계산합니다.
      </p>
      {catalog.layout && (
        <WatershedLayout
          layout={catalog.layout}
          selectedId=""
          placements={state.drafts}
          onSelect={() => {}}
          disabled={state.busy}
          selectedLinkId={draft.connectionId}
          selectableLinkIds={connections.map((c) => c.id)}
          onSelectLink={select}
        />
      )}
      <label>
        공개 관망 연결
        <select
          value={draft.connectionId}
          onChange={(e) => select(e.target.value)}
          disabled={state.busy}
        >
          {connections.map((c) => (
            <option key={c.id} value={c.id}>
              {c.id} · {c.inlet.id} → {c.receiver.id}
            </option>
          ))}
        </select>
      </label>
      <p>
        원본 관망 기준고 · {connection.inlet.id}: {number(connection.inlet.invertM)}~
        {number(connection.inlet.invertM + connection.inlet.maxDepthM)} m / {connection.receiver.id}
        : {number(connection.receiver.invertM)}~
        {number(connection.receiver.invertM + connection.receiver.maxDepthM)} m. 수직 기준면 미확인.
      </p>
      <fieldset disabled={state.busy} className="watershed-storage-fields">
        <legend>신규 시설 설계값</legend>
        <p>
          아래 값은 편집 가능한 초기 설계입니다. 실제 기존 시설의 관측 제원이 아닙니다. 100
          m²·방류계수 0.65·초기 수심 0 m를 시작값으로 사용하며 높이는 연결 절점 범위 안에서
          정합니다.
        </p>
        <div className="watershed-inputs">
          {(
            [
              ['areaM2', '바닥 면적 (m²)', 0.01, 1e6, 0.01],
              ['depthM', '저류 높이 (m)', 0.001, 100, 0.001],
              ['invertM', '바닥 기준고 (m)', -1000, 10000, 0.001],
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
        <strong className="watershed-storage-capacity">
          설계 저류 용량{' '}
          {Number.isFinite(draft.areaM2 * draft.depthM) ? number(draft.areaM2 * draft.depthM) : '—'}{' '}
          m³
        </strong>
        <details>
          <summary>유입·배수 개구부와 역류 설정</summary>
          {(Object.keys(portNames) as (keyof typeof portNames)[]).map((kind) => (
            <fieldset key={kind}>
              <legend>
                {portNames[kind]} ·{' '}
                {kind === 'inlet' ? connection.inlet.id : connection.receiver.id}
              </legend>
              {(
                [
                  ['crestM', '개구부 하단 기준고 (m)', -1000, 10000],
                  ['diameterM', '원형 구경 (m)', 0.001, 100],
                  ['dischargeCoefficient', '방류계수', 0.001, 1],
                ] as const
              ).map(([key, label, min, max]) => (
                <label key={key}>
                  {label}
                  <input
                    type="number"
                    min={min}
                    max={max}
                    step="0.001"
                    value={Number.isFinite(draft[kind][key]) ? draft[kind][key] : ''}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        [kind]: { ...draft[kind], [key]: e.target.valueAsNumber },
                      })
                    }
                  />
                </label>
              ))}
              <label className="watershed-check">
                <input
                  type="checkbox"
                  checked={draft[kind].flapGate}
                  onChange={(e) =>
                    setDraft({ ...draft, [kind]: { ...draft[kind], flapGate: e.target.checked } })
                  }
                />
                역류 방지 플랩
              </label>
            </fieldset>
          ))}
        </details>
      </fieldset>
      <p className="watershed-warning">
        현장 부지·지하 층위·공사비 미확인. 관망 설계 비교 전용이며 서울 지도 점유나 예산 차감은
        적용되지 않습니다. 선행 관측 기반 초기 수심은 미연결입니다.
      </p>
      {error && (
        <p role="alert" className="watershed-warning">
          {error}
        </p>
      )}
      {feedback && <p role="status">{feedback}</p>}
      <button
        className="watershed-secondary"
        disabled={
          state.busy ||
          state.drafts.length +
            state.storageDrafts.length +
            state.conduitDrafts.length +
            state.pumpDrafts.length >=
            20
        }
        onClick={add}
      >
        설계에 추가
      </button>
      <WatershedDesignReview catalog={catalog} state={state} />
    </section>
  );
}
