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
  const count = state.drafts.length + state.storageDrafts.length + state.conduitDrafts.length;
  const costing = state.drafts.length ? previewWatershedCosts(catalog, state.drafts) : null;
  return (
    <>
      <div className="watershed-drafts">
        <h3>공동 설계 · {count}/20곳</h3>
        {!count && <p>시설을 추가한 뒤 기준안과 비교할 수 있습니다.</p>}
        <ul>
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
        </ul>
      </div>
      <p className="watershed-warning">
        2010년 공개 원 관망 강우로 계산합니다. 현재 재생 중인 재해·실시간 강우와 별도이며 주간·재해
        예산과 순위에 반영하지 않습니다. 전체 설치비 미확정.
      </p>
      {state.conduitDrafts.length > 0 && (
        <p className="watershed-warning">관로 개량 공사비 미산정 · 참고 부분합 제외</p>
      )}
      {state.storageDrafts.length > 0 && (
        <p className="watershed-warning">
          지하 저류조 공사비 미산정 · 아래 참고 부분합에는 포함되지 않습니다.
        </p>
      )}
      {costing && (
        <WatershedCosts
          costing={costing}
          preview
          additionalUnpriced={[
            ...state.storageDrafts.map((p) => ({ id: p.id, name: '지하 저류조' })),
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
    </>
  );
}
