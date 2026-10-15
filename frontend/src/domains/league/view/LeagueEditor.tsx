import { useState } from 'react';
import type { League, LeagueDraft } from '../entity/league';
import type { Lab, FacilityType } from '../../game/entity/game';
import { facilities, won } from '../../game/service/gameService';
import { localDateTime } from '../service/leagueService';
export function LeagueEditor({
  league,
  lab,
  busy,
  onSave,
  onClose,
}: {
  league: League | null;
  lab: Lab;
  busy: boolean;
  onSave: (draft: LeagueDraft) => void;
  onClose: () => void;
}) {
  const [title, setTitle] = useState(league?.title ?? ''),
    [question, setQuestion] = useState(league?.question ?? ''),
    [opensAt] = useState(
      localDateTime(league?.rules.opensAt ?? new Date(Date.now() + 300000).toISOString())
    ),
    [closesAt] = useState(
      localDateTime(league?.rules.closesAt ?? new Date(Date.now() + 7 * 86400000).toISOString())
    ),
    [budget, setBudget] = useState(league?.rules.budget ?? lab.model.budget),
    [limit, setLimit] = useState(league?.rules.submissionLimit ?? 10),
    [types, setTypes] = useState<FacilityType[]>(
      league?.rules.allowedTypes ?? ['RAIN_GARDEN', 'PERMEABLE_PAVEMENT', 'GREEN_ROOF']
    );
  const [dateError, setDateError] = useState('');
  return (
    <form
      className="league-editor"
      onSubmit={(e) => {
        e.preventDefault();
        const values = new FormData(e.currentTarget);
        const start = new Date(String(values.get('opensAt'))),
          end = new Date(String(values.get('closesAt')));
        if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start) {
          setDateError('접수 종료는 시작 이후로 설정해 주세요.');
          return;
        }
        setDateError('');
        onSave({
          baseRevision: league?.revision ?? 0,
          title,
          question,
          opensAt: start.toISOString(),
          closesAt: end.toISOString(),
          budget,
          allowedTypes: types,
          submissionLimit: limit,
        });
      }}
    >
      <div className="page-heading">
        <h2>{league ? '리그 초안 수정' : '새 리그 초안'}</h2>
        <button type="button" className="text-button" onClick={onClose}>
          닫기
        </button>
      </div>
      <p>
        현재 모델 · {lab.model.title} / 실측 {lab.model.rainfall.totalDepthMm} mm. 지형·관망·토양
        미검증 상태의 탐색 리그입니다.
      </p>
      <label>
        리그 이름
        <input required maxLength={100} value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label>
        연구 질문
        <textarea
          required
          rows={3}
          maxLength={2000}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="어떤 배치를 비교하고, 무엇을 확인하려 하나요?"
        />
      </label>
      <div className="league-form-grid">
        <label>
          접수 시작 · 기기 시간
          <input type="datetime-local" required name="opensAt" defaultValue={opensAt} />
        </label>
        <label>
          접수 종료 · 기기 시간
          <input type="datetime-local" required name="closesAt" defaultValue={closesAt} />
        </label>
        <label>
          설치 예산 · 원
          <input
            type="number"
            required
            min={1}
            max={lab.model.budget}
            step={1}
            value={budget}
            onChange={(e) => setBudget(Number(e.target.value))}
          />
          <small>최대 {won(lab.model.budget)}, 공개 사업계획 참고 단가</small>
        </label>
        <label>
          회원별 제출 한도
          <input
            type="number"
            required
            min={1}
            max={100}
            step={1}
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
          />
        </label>
      </div>
      {dateError && (
        <p role="alert" className="form-error">
          {dateError}
        </p>
      )}
      <fieldset>
        <legend>허용 시설</legend>
        {(Object.keys(facilities) as FacilityType[]).map((t) => (
          <label className="league-check" key={t}>
            <input
              type="checkbox"
              checked={types.includes(t)}
              onChange={(e) =>
                setTypes((old) => (e.target.checked ? [...old, t] : old.filter((v) => v !== t)))
              }
            />
            {facilities[t].name}
          </label>
        ))}
      </fieldset>
      <p className="footnote">
        저장은 비공개 초안입니다. 공개 단계에서 모델·강우·시설 제원·점수·예산·기간을 고정합니다.
      </p>
      <button className="primary-button" disabled={busy || types.length === 0} type="submit">
        비공개 초안 저장
      </button>
    </form>
  );
}
