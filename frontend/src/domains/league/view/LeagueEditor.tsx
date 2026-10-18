import { useState, useEffect } from 'react';
import type { League, LeagueDraft, LeagueParticipationRules } from '../entity/league';
import { loadRainfallCatalog } from '../../game/repository/gameRepository';
import type { Lab, RainfallCatalog, FacilityType } from '../../game/entity/game';
import { facilities, won } from '../../game/service/gameService';
import { rainDate } from '../../game/service/gameTimeService';
import { localDateTime, availableLimits } from '../service/leagueService';
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
  const [participation, setParticipation] = useState<LeagueParticipationRules>(
    league?.rules.participation ?? {
      access: 'PUBLIC',
      admission: 'OPEN',
      entryMode: 'INDIVIDUAL',
      teamSizeLimit: null,
    }
  );
  const maximum = availableLimits(lab, types);
  const [placementLimit, setPlacementLimit] = useState(
    league?.rules.placementLimit ?? maximum.placementLimit
  );
  const [areaLimit, setAreaLimit] = useState(league?.rules.areaLimitM2 ?? maximum.areaLimitM2);
  const [dateError, setDateError] = useState('');
  const [modelHash, setModelHash] = useState(league?.rules.modelHash ?? lab.modelHash);
  const [catalog, setCatalog] = useState<RainfallCatalog | null>(null);
  useEffect(() => {
    let alive = true;
    loadRainfallCatalog()
      .then((v) => {
        if (alive) setCatalog(v);
      })
      .catch(() => {
        if (alive) setDateError('강우 목록을 불러오지 못했습니다. 잠시 후 다시 열어 주세요.');
      });
    return () => {
      alive = false;
    };
  }, []);
  const chosen = catalog?.models.find((m) => m.modelHash === modelHash);
  return (
    <form
      className="league-editor"
      onSubmit={(e) => {
        e.preventDefault();
        const values = new FormData(e.currentTarget);
        const award = {
          prizeKrw: Number(values.get('prizeKrw')),
          winnerCount: Number(values.get('winnerCount')),
          notice: String(values.get('awardNotice')).trim(),
        };
        if (
          (award.prizeKrw === 0 && award.winnerCount !== 0) ||
          (award.prizeKrw > 0 && (award.winnerCount < 1 || award.notice.length < 10))
        ) {
          setDateError(
            '상금이 있으면 수상 예정 인원과 10자 이상의 안내가 필요합니다. 상금이 없으면 인원도 0으로 설정해 주세요.'
          );
          return;
        }
        const start = new Date(String(values.get('opensAt'))),
          end = new Date(String(values.get('closesAt')));
        if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start) {
          setDateError('접수 종료는 시작 이후로 설정해 주세요.');
          return;
        }
        const now = Date.now();
        if (
          start.getTime() < now - 600000 ||
          end.getTime() <= now ||
          end.getTime() > now + 366 * 86400000
        ) {
          setDateError(
            '접수 시작은 현재보다 10분 이전일 수 없으며, 종료는 현재 이후 366일 이내로 설정해 주세요.'
          );
          return;
        }
        setDateError('');
        onSave({
          modelHash,
          baseRevision: league?.revision ?? 0,
          title,
          question,
          opensAt: start.toISOString(),
          closesAt: end.toISOString(),
          budget,
          allowedTypes: types,
          submissionLimit: limit,
          placementLimit,
          areaLimitM2: areaLimit,
          award,
          participation,
        });
      }}
    >
      <div className="page-heading">
        <h2>{league ? '리그 초안 수정' : '새 리그 초안'}</h2>
        <button type="button" className="text-button" disabled={busy} onClick={onClose}>
          닫기
        </button>
      </div>
      <p>지형·관망·토양 미검증 상태의 탐색 리그입니다. 공개 후 강우 조건이 고정됩니다.</p>
      <label>
        고정할 관측 강우
        <select
          value={modelHash}
          onChange={(e) => setModelHash(e.target.value)}
          disabled={!catalog}
        >
          {catalog?.models.map((m) => (
            <option key={m.modelHash} value={m.modelHash}>
              {m.mapTitle ?? '기존 지도'} · {m.rainfall.stationName} {rainDate(m.rainfall.start)} ·{' '}
              {m.rainfall.totalDepthMm} mm
            </option>
          ))}
        </select>
      </label>
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
            max={chosen?.budget ?? lab.model.budget}
            step={1}
            value={budget}
            onChange={(e) => setBudget(Number(e.target.value))}
          />
          <small>최대 {won(chosen?.budget ?? lab.model.budget)}, 공개 사업계획 참고 단가</small>
        </label>
        <label>
          {participation.entryMode === 'TEAM' ? '팀 전체 제출 한도' : '회원별 제출 한도'}
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
        <label>
          시설 배치 구역 수 상한
          <input
            type="number"
            required
            min={1}
            max={maximum.placementLimit}
            step={1}
            value={placementLimit}
            onChange={(e) => setPlacementLimit(Number(e.target.value))}
          />
          <small>시설을 배치한 구역 한 곳을 1개로 계산합니다.</small>
        </label>
        <label>
          전체 설치 면적 상한 · m²
          <input
            type="number"
            required
            min={0.01}
            max={maximum.areaLimitM2}
            step={0.01}
            value={areaLimit}
            onChange={(e) => setAreaLimit(Number(e.target.value))}
          />
          <small>각 구역의 설치 가능 면적도 함께 적용합니다.</small>
        </label>
      </div>
      {dateError && (
        <p role="alert" className="form-error">
          {dateError}
        </p>
      )}
      <fieldset className="league-entry-rules">
        <legend>참가 방식</legend>
        <div className="league-form-grid">
          <label>
            리그 공개 범위
            <select
              value={participation.access}
              onChange={(e) =>
                setParticipation((p) => ({
                  ...p,
                  access: e.target.value as LeagueParticipationRules['access'],
                }))
              }
            >
              <option value="PUBLIC">전체 공개</option>
              <option value="INVITE">초대 전용</option>
            </select>
          </label>
          <label>
            참가 승인 방식
            <select
              value={participation.admission}
              onChange={(e) =>
                setParticipation((p) => ({
                  ...p,
                  admission: e.target.value as LeagueParticipationRules['admission'],
                }))
              }
            >
              <option value="OPEN">즉시 참가</option>
              <option value="APPROVAL">주최자 승인 후 참가</option>
            </select>
          </label>
          <label>
            경쟁 단위
            <select
              value={participation.entryMode}
              onChange={(e) =>
                setParticipation((p) => ({
                  ...p,
                  entryMode: e.target.value as LeagueParticipationRules['entryMode'],
                  teamSizeLimit: e.target.value === 'TEAM' ? (p.teamSizeLimit ?? 4) : null,
                }))
              }
            >
              <option value="INDIVIDUAL">개인전</option>
              <option value="TEAM">팀전</option>
            </select>
          </label>
          {participation.entryMode === 'TEAM' && (
            <label>
              팀 최대 인원
              <input
                required
                type="number"
                min={2}
                max={10}
                step={1}
                value={participation.teamSizeLimit ?? 4}
                onChange={(e) =>
                  setParticipation((p) => ({ ...p, teamSizeLimit: Number(e.target.value) }))
                }
              />
            </label>
          )}
        </div>
        <p className="footnote">
          초대 전용 리그는 공개 목록에 표시되지 않습니다. 발행 후 리그 코드를 발급합니다. 팀전은
          제출 한도를 공유하며 첫 제출 후 팀원이 고정됩니다.
        </p>
      </fieldset>
      <fieldset>
        <legend>허용 시설</legend>
        {(Object.keys(facilities) as FacilityType[]).map((t) => (
          <label className="league-check" key={t}>
            <input
              type="checkbox"
              checked={types.includes(t)}
              onChange={(e) => {
                const next = e.target.checked ? [...types, t] : types.filter((v) => v !== t);
                setTypes(next);
                const upper = availableLimits(lab, next);
                setPlacementLimit((old) => Math.min(Math.max(old, 1), upper.placementLimit));
                setAreaLimit((old) => Math.min(Math.max(old, 0.01), upper.areaLimitM2));
              }}
            />
            {facilities[t].name}
          </label>
        ))}
      </fieldset>
      <fieldset className="league-award-editor">
        <legend>상금·심사 안내</legend>
        <div className="league-form-grid">
          <label>
            총상금 · 원
            <input
              name="prizeKrw"
              type="number"
              required
              min={0}
              max={1000000000}
              step={1}
              defaultValue={league?.rules.award?.prizeKrw ?? 0}
            />
          </label>
          <label>
            수상 예정 인원
            <input
              name="winnerCount"
              type="number"
              required
              min={0}
              max={1000}
              step={1}
              defaultValue={league?.rules.award?.winnerCount ?? 0}
            />
          </label>
        </div>
        <label>
          선정 기준·동점 처리·지급 일정 안내
          <textarea
            name="awardNotice"
            rows={4}
            maxLength={2000}
            defaultValue={league?.rules.award?.notice ?? ''}
            placeholder="상금이 있으면 10자 이상으로 선정 기준과 지급 계획을 설명하세요."
          />
        </label>
        <p className="footnote">
          상금이 없으면 금액과 인원을 0으로 설정합니다. 수상 선정·지급은 주최 기관이 담당하며
          계좌·연락처 등 개인정보는 입력하지 마세요. 게임 순위는 고정 점수로 계산됩니다.
        </p>
      </fieldset>
      <p className="footnote">
        저장은 비공개 초안입니다. 공개 단계에서 모델·강우·시설·배치 제한·점수·예산·기간·상금 안내와
        참가 방식을 고정합니다.
      </p>
      <button
        className="primary-button"
        disabled={busy || types.length === 0 || !chosen}
        type="submit"
      >
        비공개 초안 저장
      </button>
    </form>
  );
}
