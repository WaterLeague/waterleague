import { CisternReferenceCosts } from './CisternReferenceCosts';
import { previewCisternCosts } from '../service/cisternCosts';
import { conduitDimensions } from '../service/conduitDesign';
import type { WatershedState } from '../controller/useWatershed';
import type { WatershedCatalog } from '../dto/watershedDto';
import { networkNames } from '../service/watershedDesign';
import { previewWatershedCosts } from '../service/watershedCosts';
import { physicalAmount as number } from '../../physics/service/physicalValueFormat';
import { WatershedCosts } from './WatershedCosts';
export function WatershedDesignReview({
  catalog,
  state,
}: {
  catalog: WatershedCatalog;
  state: WatershedState;
}) {
  const cisternCosting = previewCisternCosts(catalog, state.drafts, state.cisternDraft);
  const count =
    state.drafts.length +
    state.storageDrafts.length +
    state.conduitDrafts.length +
    state.pumpDrafts.length +
    (state.cisternDraft ? 1 : 0);
  const costing = state.drafts.length ? previewWatershedCosts(catalog, state.drafts) : null;
  return (
    <>
      <div className="watershed-drafts">
        <h3>공동 설계 · {count}/20곳</h3>
        {!count && <p>시설을 추가한 뒤 기준안과 비교할 수 있습니다.</p>}
        <ul>
          {state.cisternDraft && (
            <li>
              <div>
                <strong>{state.cisternDraft.catchmentId} · 빗물이용조</strong>
                <span>
                  집수 {number(state.cisternDraft.captureAreaM2)} m² · 용량{' '}
                  {number(state.cisternDraft.areaM2 * state.cisternDraft.depthM)} m³
                  {' · '}
                  {state.cisternDraft.drainClosed ? '일반 배출 중지' : '자연배수'}
                  {' · '}
                  {state.cisternDraft.inletPipe ? '집수 연결관 수리 계산' : '집수 직접 연결'}
                </span>
              </div>
              <button
                aria-label="이용조 수리 설계 삭제"
                disabled={state.busy}
                onClick={() => state.setCisternDraft(null)}
              >
                삭제
              </button>
            </li>
          )}
          {state.drafts.map((p) => (
            <li key={p.id}>
              <div>
                <strong>
                  {p.catchmentId} · {networkNames[p.facilityType]}
                </strong>
                <span>
                  {number(p.areaM2)} m² · 추가 처리 {number(p.treatedImperviousM2)} m²
                </span>
              </div>
              <button
                aria-label={`${p.id} ${networkNames[p.facilityType]} 삭제`}
                disabled={state.busy}
                onClick={() => state.setDrafts(state.drafts.filter((d) => d.id !== p.id))}
              >
                삭제
              </button>
            </li>
          ))}
          {state.storageDrafts.map((p) => (
            <li key={p.id}>
              <div>
                <strong>{p.connectionId} · 지하 저류조</strong>
                <span>
                  {number(p.areaM2 * p.depthM)} m³ · {number(p.areaM2)} m² × {number(p.depthM)} m
                </span>
              </div>
              <button
                aria-label={`${p.id} 지하 저류조 삭제`}
                disabled={state.busy}
                onClick={() =>
                  state.setStorageDrafts(state.storageDrafts.filter((d) => d.id !== p.id))
                }
              >
                삭제
              </button>
            </li>
          ))}
          {state.conduitDrafts.map((p) => (
            <li key={p.id}>
              <div>
                <strong>{p.conduitId} · 배수관·암거 개량</strong>
                <span>{conduitDimensions(p)}</span>
              </div>
              <button
                aria-label={`${p.id} 관로 개량 삭제`}
                disabled={state.busy}
                onClick={() =>
                  state.setConduitDrafts(state.conduitDrafts.filter((c) => c.id !== p.id))
                }
              >
                삭제
              </button>
            </li>
          ))}
          {state.pumpDrafts.map((p) => (
            <li key={p.id}>
              <div>
                <strong>{p.id} · 빗물펌프장</strong>
                <span>
                  {p.fromNode} → {p.toNode} · 기동/정지 {p.startDepthM}/{p.stopDepthM} m
                </span>
              </div>
              <button
                aria-label={`${p.id} 펌프 설계 삭제`}
                disabled={state.busy}
                onClick={() => state.setPumpDrafts(state.pumpDrafts.filter((v) => v.id !== p.id))}
              >
                삭제
              </button>
            </li>
          ))}
        </ul>
      </div>
      <p className="watershed-warning">
        2010년 공개 원 관망 강우로 계산합니다. 현재 재생 중인 재해·실시간 강우와 별도이며 주간·재해
        예산과 순위에 반영하지 않습니다. 전체 설치비 미확정.
      </p>
      {state.pumpDrafts.length > 0 && (
        <p className="watershed-warning">펌프·압력관 공사비 미산정 · 참고 부분합 제외</p>
      )}
      {state.conduitDrafts.length > 0 && (
        <p className="watershed-warning">관로 개량 공사비 미산정 · 참고 부분합 제외</p>
      )}
      {state.storageDrafts.length > 0 && (
        <p className="watershed-warning">
          지하 저류조 공사비 미산정 · 아래 참고 부분합에는 포함되지 않습니다.
        </p>
      )}
      {cisternCosting && <CisternReferenceCosts costing={cisternCosting} preview />}
      {costing && (
        <WatershedCosts
          costing={costing}
          cisternQuoteIds={cisternCosting?.items.map((i) => i.placementId)}
          preview
          additionalUnpriced={[
            ...state.storageDrafts.map((p) => ({ id: p.id, name: '지하 저류조' })),
            ...state.pumpDrafts.map((p) => ({ id: p.id, name: '빗물펌프장·압력관' })),
            ...state.conduitDrafts.map((p) => ({ id: p.id, name: '배수관·암거 개량' })),
          ]}
        />
      )}
      <button
        type="button"
        className="watershed-submit"
        disabled={state.busy || !count}
        onClick={() => void state.submit()}
      >
        {state.busy ? '요청 중…' : '기준안과 관망 계산 비교'}
      </button>
      {catalog.surfaceProfile && (
        <>
          <button
            type="button"
            className="watershed-submit"
            disabled={
              state.busy ||
              !state.drafts.length ||
              Boolean(state.cisternDraft) ||
              state.storageDrafts.length > 0 ||
              state.conduitDrafts.length > 0 ||
              state.pumpDrafts.length > 0 ||
              state.drafts.some((p) => p.facilityType === 'RAINWATER_CISTERN')
            }
            onClick={() => void state.submit(true)}
          >
            지표 수심까지 함께 비교
          </button>
          <p>
            생물저류·침투도랑·식생수로는 공개 지형을 포함해 비교할 수 있습니다. 계산에는 수 분 이상
            걸리며 창을 닫아도 계속됩니다.
          </p>
          <details>
            <summary>지표 계산에 적용되는 가정</summary>
            {catalog.surfaceProfile.limitations.map((text) => (
              <p key={text}>{text}</p>
            ))}
          </details>
        </>
      )}
    </>
  );
}
