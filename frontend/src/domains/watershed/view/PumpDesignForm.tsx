import { useState } from 'react';
import type { WatershedState } from '../controller/useWatershed';
import type { WatershedCatalog } from '../dto/watershedDto';
import type { PumpDelivery, PumpPlacement } from '../dto/pumpDto';
import { pumpNodes, pumpReceivers } from '../service/pumpDesign';
import { validateCombinedDesign } from '../service/storageDesign';
import { WatershedDesignReview } from './WatershedDesignReview';
import { physicalAmount as number } from '../../physics/service/physicalValueFormat';

export function PumpDesignForm({
  catalog,
  state,
}: {
  catalog: WatershedCatalog;
  state: WatershedState;
}) {
  if (!catalog.pumpCatalog || !catalog.layout || !catalog.storageCatalog)
    return <p>펌프 성능자료와 관망 연결을 조회 중입니다.</p>;
  return <Composer key={catalog.pumpCatalogHash} catalog={catalog} state={state} />;
}
function Composer({ catalog, state }: { catalog: WatershedCatalog; state: WatershedState }) {
  const curve = catalog.pumpCatalog!,
    nodes = pumpNodes(catalog, state.storageDrafts);
  const [draft, setDraft] = useState<PumpPlacement>(() => {
    const from = state.storageDrafts[0]
      ? 'WLST_' + state.storageDrafts[0].id
      : (nodes.sources[0]?.id ?? '');
    return {
      id: 'Pump1',
      fromNode: from,
      toNode: pumpReceivers(catalog, state.storageDrafts, from)[0]?.id ?? '',
      startDepthM: 1.8,
      stopDepthM: 1.2,
      initialStatus: 'OFF',
      delivery: {
        lengthM: 10,
        diameterM: 0.5,
        roughnessMm: 0.1,
        pressureHeadLimitM: 20,
        entranceLoss: 0.5,
        exitLoss: 1,
        averageLoss: 0,
        checkValve: true,
      },
    };
  });
  const [error, setError] = useState(''),
    [feedback, setFeedback] = useState('');
  const receivers = pumpReceivers(catalog, state.storageDrafts, draft.fromNode);
  const source = nodes.sources.find((n) => n.id === draft.fromNode);
  const maxHead = Math.max(...curve.points.map((p) => p.headM)),
    minHead = Math.min(...curve.points.map((p) => p.headM));
  const qmin = curve.points[0].flowM3h,
    qmax = curve.points.at(-1)!.flowM3h;
  function add() {
    let i = 1;
    const used = new Set(
      [...state.drafts, ...state.storageDrafts, ...state.conduitDrafts, ...state.pumpDrafts].map(
        (p) => p.id.toUpperCase()
      )
    );
    while (used.has('PUMP' + i)) i++;
    const next = [...state.pumpDrafts, { ...draft, id: 'Pump' + i }];
    const invalid = validateCombinedDesign(
      catalog,
      state.drafts,
      state.storageDrafts,
      state.conduitDrafts,
      next,
      state.cisternDraft
    );
    setError(invalid);
    setFeedback('');
    if (!invalid) {
      state.setPumpDrafts(next);
      setFeedback(`${draft.fromNode} → ${draft.toNode} 펌프 설계 추가`);
    }
  }
  const fields: [keyof Omit<PumpDelivery, 'checkValve'>, string, number, number][] = [
    ['lengthM', '접속 압력관 길이 (m)', 0.001, 10000],
    ['diameterM', '압력관 내경 (m)', 0.001, 20],
    ['roughnessMm', '압력관 절대조도 (mm)', 0.001, 100],
    ['pressureHeadLimitM', '토출부 허용 압력수두 (m)', 0.001, 1000],
    ['entranceLoss', '입구 손실계수', 0, 100],
    ['exitLoss', '출구 손실계수', 0, 100],
    ['averageLoss', '중간 손실계수', 0, 100],
  ];
  return (
    <section className="watershed-composer" aria-label="빗물펌프장 설계">
      <h3>빗물펌프장 설계</h3>
      <p>
        저류조 또는 공개 관망 지점의 물을 연결된 하류로 이송합니다. 수위차와 압력관 손실에 따라
        유량이 달라집니다.
      </p>
      <div className="watershed-facility-state">
        <strong>
          {curve.model} · {curve.frequencyHz} Hz
        </strong>
        <p>
          {curve.speedRpm} rpm · 날개각 {curve.bladeAngleDeg}° · 제조사 공개 곡선
        </p>
        <svg
          className="watershed-pump-curve"
          viewBox="0 0 320 150"
          role="img"
          aria-label={`펌프 성능곡선: 유량 ${qmin}~${qmax} 세제곱미터 매시, 양정 ${number(minHead)}~${number(maxHead)} 미터`}
        >
          <path d="M44 18 V116 H302" fill="none" stroke="currentColor" opacity=".3" />
          <polyline
            fill="none"
            stroke="#387b98"
            strokeWidth="3"
            points={curve.points
              .map(
                (p) =>
                  `${44 + ((p.flowM3h - qmin) / (qmax - qmin)) * 250},${116 - (p.headM / maxHead) * 94}`
              )
              .join(' ')}
          />
          <text x="4" y="24">
            {number(maxHead)} m
          </text>
          <text x="44" y="138">
            {qmin}
          </text>
          <text x="222" y="138">
            {qmax} m³/h
          </text>
        </svg>
        <p>서울 기존 펌프의 실측 제원이 아닙니다. 공개 구간 밖 운전은 실패로 표시합니다.</p>
        <a href={curve.source.url} target="_blank" rel="noreferrer">
          {curve.source.author} · 원문 {curve.source.page}쪽
        </a>
      </div>
      <fieldset className="watershed-storage-fields" disabled={state.busy}>
        <legend>연결과 운전</legend>
        <p>
          아래 초기값은 수정 가능한 설계 예시입니다. 현장 관측값이 아닙니다. 낮은 저류조에서 하류로
          양수하는 설계를 비교할 수 있습니다.
        </p>
        <label>
          펌프 흡입 지점
          <select
            value={draft.fromNode}
            onChange={(e) => {
              const from = e.target.value;
              setDraft({
                ...draft,
                fromNode: from,
                toNode: pumpReceivers(catalog, state.storageDrafts, from)[0]?.id ?? '',
              });
            }}
          >
            {nodes.sources.map((n) => (
              <option key={n.id} value={n.id}>
                {n.id.startsWith('WLST_') ? '내 저류조 ' + n.id.slice(5) : n.id} · 바닥 {n.invertM}{' '}
                m
              </option>
            ))}
          </select>
        </label>
        <label>
          펌프 토출 하류 지점
          <select
            value={draft.toNode}
            onChange={(e) => setDraft({ ...draft, toNode: e.target.value })}
          >
            {!receivers.length && <option value="">연결 가능한 내부 지점 없음</option>}
            {receivers.map((n) => (
              <option key={n.id} value={n.id}>
                {n.id} · 바닥 {n.invertM} m
              </option>
            ))}
          </select>
        </label>
        <p>
          수심은 흡입 지점 바닥 기준 · 최대 {source?.maxDepthM ?? '미확인'} m. 절점 표고는 원 관망의
          상대 기준이며 해발고로 확정되지 않았습니다.
        </p>
        <div className="watershed-inputs">
          {(
            [
              ['startDepthM', '기동 수심 (m)'],
              ['stopDepthM', '정지 수심 (m)'],
            ] as const
          ).map(([key, label]) => (
            <label key={key}>
              {label}
              <input
                type="number"
                min="0.001"
                max={source?.maxDepthM ?? 100}
                step="0.001"
                value={Number.isFinite(draft[key]) ? draft[key] : ''}
                onChange={(e) => setDraft({ ...draft, [key]: e.target.valueAsNumber })}
              />
            </label>
          ))}
        </div>
        <label>
          초기 펌프 상태
          <select
            value={draft.initialStatus}
            onChange={(e) => setDraft({ ...draft, initialStatus: e.target.value as 'ON' | 'OFF' })}
          >
            <option value="OFF">정지</option>
            <option value="ON">운전</option>
          </select>
        </label>
      </fieldset>
      <fieldset className="watershed-storage-fields" disabled={state.busy}>
        <legend>접속 압력관</legend>
        <p>
          수신 절점과 같은 바닥 높이의 접속 설계입니다. 길이·내경·절대조도에 따른 마찰과 국부손실을
          계산합니다.
        </p>
        <div className="watershed-inputs">
          {fields.map(([key, label, min, max]) => (
            <label key={key}>
              {label}
              <input
                type="number"
                min={min}
                max={max}
                step="0.001"
                value={Number.isFinite(draft.delivery[key]) ? draft.delivery[key] : ''}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    delivery: { ...draft.delivery, [key]: e.target.valueAsNumber },
                  })
                }
              />
            </label>
          ))}
        </div>
        <label>
          <input
            type="checkbox"
            checked={draft.delivery.checkValve}
            onChange={(e) =>
              setDraft({ ...draft, delivery: { ...draft.delivery, checkValve: e.target.checked } })
            }
          />
          압력관 역류방지판
        </label>
      </fieldset>
      <p className="watershed-warning">
        공사비 미산정 · 최소 잠김과 캐비테이션 안전성 미평가. 축동력은 전기 사용량과 다릅니다.
      </p>
      {error && <p role="alert">{error}</p>}
      {feedback && <p role="status">{feedback}</p>}
      <button className="watershed-add" disabled={state.busy || !draft.toNode} onClick={add}>
        펌프 설계 추가
      </button>
      <WatershedDesignReview catalog={catalog} state={state} />
    </section>
  );
}
