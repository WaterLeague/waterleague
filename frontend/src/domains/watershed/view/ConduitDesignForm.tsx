import { useState } from 'react';
import type { WatershedState } from '../controller/useWatershed';
import type { WatershedCatalog } from '../dto/watershedDto';
import type { ConduitPlacement } from '../dto/conduitDto';
import { conduitDimensions } from '../service/conduitDesign';
import { validateCombinedDesign } from '../service/storageDesign';
import { WatershedLayout } from './WatershedLayout';
import { WatershedDesignReview } from './WatershedDesignReview';
export function ConduitDesignForm({
  catalog,
  state,
}: {
  catalog: WatershedCatalog;
  state: WatershedState;
}) {
  if (!catalog.conduitCatalog?.conduits.length)
    return <p>이 관망 버전에는 관로 개량 자료가 없습니다.</p>;
  return <Composer key={catalog.conduitCatalogHash} catalog={catalog} state={state} />;
}
function Composer({ catalog, state }: { catalog: WatershedCatalog; state: WatershedState }) {
  const rows = catalog.conduitCatalog!.conduits;
  const initial = (id: string): ConduitPlacement => ({
    id: 'Pipe1',
    conduitId: id,
    ...rows.find((c) => c.id === id)!.original,
  });
  const [draft, setDraft] = useState(() => initial(rows[0].id));
  const [error, setError] = useState(''),
    [feedback, setFeedback] = useState('');
  const source = rows.find((c) => c.id === draft.conduitId)!;
  function select(id: string) {
    setDraft(initial(id));
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
    while (used.has(`PIPE${i}`)) i++;
    const next = [...state.conduitDrafts, { ...draft, id: `Pipe${i}` }];
    const invalid = validateCombinedDesign(
      catalog,
      state.drafts,
      state.storageDrafts,
      next,
      state.pumpDrafts,
      state.cisternDraft
    );
    setError(invalid);
    setFeedback('');
    if (!invalid) {
      state.setConduitDrafts(next);
      setFeedback(`${draft.conduitId} 관로 개량 설계 추가`);
    }
  }
  return (
    <section className="watershed-composer" aria-label="배수관·암거 설계">
      <h3>배수관·암거 개량</h3>
      <p>
        기존 공개 관로의 단면과 마찰을 변경합니다. 원본 접속·길이·관저고·외부 경계를 유지하고, 바뀐
        흐름을 관망 전체에서 계산합니다.
      </p>
      {catalog.layout && (
        <WatershedLayout
          layout={catalog.layout}
          selectedId=""
          placements={state.drafts}
          onSelect={() => {}}
          selectedLinkId={draft.conduitId}
          selectableLinkIds={rows.map((c) => c.id)}
          onSelectLink={select}
          disabled={state.busy}
          linkSelectionLabel="파란색: 개량할 기존 관로"
        />
      )}
      <label>
        개량할 공개 관로
        <select
          value={draft.conduitId}
          disabled={state.busy}
          onChange={(e) => select(e.target.value)}
        >
          {rows.map((c) => (
            <option key={c.id} value={c.id}>
              {c.id} · {c.fromNode} → {c.toNode} · {c.lengthM} m
            </option>
          ))}
        </select>
      </label>
      <div className="watershed-facility-state">
        <strong>공개 원본 제원</strong>
        <p>{conduitDimensions(source.original)}</p>
        <p>
          {source.fromNode} → {source.toNode} · 길이 {source.lengthM} m · 유입/유출 관저고 오프셋{' '}
          {source.inletOffsetM}/{source.outletOffsetM} m
        </p>
      </div>
      <p>
        공개 절점 깊이와 원 관저고 오프셋에 따른 내부 높이 한계 {source.maxFullDepthM} m · 현장 허가
        한도 아님
      </p>
      <fieldset className="watershed-storage-fields" disabled={state.busy}>
        <legend>개량 설계 제원</legend>
        <p>
          선택 시 원본 값으로 시작합니다. 수정한 치수·개수·조도는 사용자의 설계값이며 현장 시공
          가능성을 뜻하지 않습니다.
        </p>
        <label>
          관로 단면
          <select
            value={draft.shape}
            onChange={(e) =>
              setDraft({
                ...draft,
                shape: e.target.value as ConduitPlacement['shape'],
                widthM: e.target.value === 'CIRCULAR' ? null : (draft.widthM ?? draft.fullDepthM),
              })
            }
          >
            <option value="RECT_CLOSED">직사각형 폐합 암거</option>
            <option value="CIRCULAR">원형 배수관</option>
          </select>
        </label>
        <div className="watershed-inputs">
          <label>
            {draft.shape === 'CIRCULAR' ? '내경 (m)' : '내부 높이 (m)'}
            <input
              type="number"
              min="0.01"
              max={source.maxFullDepthM}
              step="0.001"
              value={Number.isFinite(draft.fullDepthM) ? draft.fullDepthM : ''}
              onChange={(e) => setDraft({ ...draft, fullDepthM: e.target.valueAsNumber })}
            />
          </label>
          {draft.shape === 'RECT_CLOSED' && (
            <label>
              내부 폭 (m)
              <input
                type="number"
                min="0.01"
                max="100"
                step="0.001"
                value={draft.widthM !== null && Number.isFinite(draft.widthM) ? draft.widthM : ''}
                onChange={(e) => setDraft({ ...draft, widthM: e.target.valueAsNumber })}
              />
            </label>
          )}
          <label>
            병렬 관 개수
            <input
              type="number"
              min="1"
              max="20"
              step="1"
              value={Number.isFinite(draft.barrels) ? draft.barrels : ''}
              onChange={(e) => setDraft({ ...draft, barrels: e.target.valueAsNumber })}
            />
          </label>
          <label>
            Manning 조도
            <input
              type="number"
              min="0.001"
              max="1"
              step="0.0001"
              value={Number.isFinite(draft.roughness) ? draft.roughness : ''}
              onChange={(e) => setDraft({ ...draft, roughness: e.target.valueAsNumber })}
            />
          </label>
        </div>
      </fieldset>
      <p className="watershed-warning">
        현장 매설 깊이·지장물·공사비 미확인. 관로를 넓혀도 하류 방류가 늘거나 다른 절점의 월류가
        커질 수 있습니다. 변경 제원은 새 계산에만 적용됩니다.
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
