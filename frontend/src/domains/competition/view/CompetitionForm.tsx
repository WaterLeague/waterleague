import { useRef, useState } from 'react';
import { Plus, X } from 'lucide-react';
import { won } from '../../game/service/gameService';
import { errorMessage } from '../../../shared/exception/ApiError';
import { createCompetition } from '../repository/competitionRepository';
import type {
  Award,
  Competition,
  CompetitionCatalog,
  CompetitionCreate,
} from '../dto/competitionDto';
import { CompetitionDistrictPicker } from './CompetitionDistrictPicker';
import { CompetitionFacilityPicker } from './CompetitionFacilityPicker';
const kstInput = (time: number) => new Date(time + 9 * 3600000).toISOString().slice(0, 16);
export function CompetitionForm({
  catalog,
  onCreated,
  onClose,
}: {
  catalog: CompetitionCatalog;
  onCreated: (v: Competition) => void;
  onClose: () => void;
}) {
  const [budgetMode, setBudgetMode] = useState<'DEFAULT' | 'CUSTOM'>('DEFAULT');
  const [customBudget, setCustomBudget] = useState('');
  const [mode, setMode] = useState<Competition['mode']>('REALTIME');
  const [districts, setDistricts] = useState<string[]>([]);
  const [types, setTypes] = useState<CompetitionCatalog['facilityTypes']>([]);
  const [awards, setAwards] = useState<(Award & { key: string })[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const request = useRef<{ payload: string; key: string } | null>(null);
  const now = Date.parse(catalog.serverNow);
  const total = awards.reduce(
    (sum, a) => sum + Math.max(0, a.rankTo - a.rankFrom + 1) * a.prizeKrw,
    0
  );
  function changeAward(key: string, field: keyof Award, value: string) {
    setAwards((v) =>
      v.map((a) =>
        a.key === key ? { ...a, [field]: field === 'title' ? value : Number(value) } : a
      )
    );
  }
  async function submit(form: HTMLFormElement) {
    if (pending.current) return;
    const data = new FormData(form);
    if (!districts.length || !types.length) {
      setError('지역과 시설을 각각 하나 이상 선택해 주세요.');
      return;
    }
    const personalBudgetKrw = budgetMode === 'CUSTOM' ? Number(customBudget) : null;
    if (
      personalBudgetKrw !== null &&
      (!Number.isSafeInteger(personalBudgetKrw) ||
        personalBudgetKrw < 1 ||
        personalBudgetKrw > 1_000_000_000_000)
    ) {
      setError('1인당 예산은 1원부터 1조 원까지의 정수로 입력해 주세요.');
      return;
    }
    const opensAt = new Date(`${data.get('opensAt')}:00+09:00`).toISOString();
    const closesAt = new Date(`${data.get('closesAt')}:00+09:00`).toISOString();
    if (closesAt <= opensAt) {
      setError('종료 시각은 시작 시각보다 늦어야 합니다.');
      return;
    }
    const ranks = new Set<number>();
    for (const award of awards) {
      if (award.rankFrom > award.rankTo) {
        setError('시상 순위 범위를 확인해 주세요.');
        return;
      }
      for (let rank = award.rankFrom; rank <= award.rankTo; rank++) {
        if (ranks.has(rank)) {
          setError('시상 순위는 중복될 수 없습니다.');
          return;
        }
        ranks.add(rank);
      }
    }
    if (total > 1_000_000_000) {
      setError('총상금은 10억 원 이하여야 합니다.');
      return;
    }
    const body = {
      title: String(data.get('title')).trim(),
      description: String(data.get('description')).trim(),
      mode,
      budgetMode,
      personalBudgetKrw,
      eventId: mode === 'DISASTER' ? String(data.get('eventId')) : null,
      districtIds: districts,
      allowedTypes: types,
      opensAt,
      closesAt,
      awards: awards.map(({ key: _key, ...a }) => a),
      awardNotice: String(data.get('awardNotice') ?? '').trim(),
    };
    const payload = JSON.stringify(body);
    if (request.current?.payload !== payload)
      request.current = { payload, key: crypto.randomUUID() };
    pending.current = true;
    setBusy(true);
    setError('');
    try {
      onCreated(
        await createCompetition({
          ...body,
          requestKey: request.current!.key,
        } satisfies CompetitionCreate)
      );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <section className="contest-panel">
      <div className="contest-heading">
        <div>
          <small>HOST A COMPETITION</small>
          <h2>대회 개최</h2>
        </div>
        <button className="icon-button" aria-label="개최 폼 닫기" disabled={busy} onClick={onClose}>
          <X size={20} />
        </button>
      </div>
      <p>
        공개하면 참가 조건이 고정됩니다. 시상과 상금 지급은 주최 기관이 안내한 기준에 따라
        진행합니다.
      </p>
      <form
        className="contest-form"
        onSubmit={(e) => {
          e.preventDefault();
          void submit(e.currentTarget);
        }}
      >
        <fieldset disabled={busy}>
          <label>
            대회 이름
            <input name="title" required maxLength={100} placeholder="대회 이름을 입력하세요" />
          </label>
          <label>
            대회 소개
            <textarea
              name="description"
              required
              maxLength={4000}
              rows={4}
              placeholder="목표, 참가 안내와 운영 정보를 입력하세요"
            />
          </label>
          <div className="contest-form-grid">
            <label>
              게임 모드
              <select value={mode} onChange={(e) => setMode(e.target.value as Competition['mode'])}>
                <option value="REALTIME">실시간 모드</option>
                <option value="DISASTER">재해 모드</option>
              </select>
            </label>
            {mode === 'DISASTER' && (
              <label>
                재해 사건
                <select name="eventId" required>
                  {catalog.events.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.title}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
          <p className="contest-note">
            {mode === 'REALTIME'
              ? '참가 신청과 대회 시작 이후 설치한 시설을 집계합니다. 소속 구와 관계없이 대회에서 선택한 모든 구에 대회 전용 예산으로 설치하며 종료 시각까지 집계합니다.'
              : '지정 재해의 전체 기간을 계산한 설계를 제출합니다. 같은 평가 조건별로 회원의 최고 기록을 비교합니다.'}
          </p>
          <fieldset>
            <legend>1인당 예산</legend>
            <div className="contest-budget-options">
              <label
                className={`contest-budget-option${budgetMode === 'DEFAULT' ? ' is-selected' : ''}`}
              >
                <input
                  type="radio"
                  name="budgetMode"
                  value="DEFAULT"
                  checked={budgetMode === 'DEFAULT'}
                  onChange={() => setBudgetMode('DEFAULT')}
                />
                <span>
                  <strong>기본 예산 사용</strong>
                  <small>
                    {catalog.defaultPersonalBudgetKrw
                      ? won(catalog.defaultPersonalBudgetKrw)
                      : '기본 게임 예산'}
                  </small>
                </span>
              </label>
              <label
                className={`contest-budget-option${budgetMode === 'CUSTOM' ? ' is-selected' : ''}`}
              >
                <input
                  type="radio"
                  name="budgetMode"
                  value="CUSTOM"
                  checked={budgetMode === 'CUSTOM'}
                  onChange={() => setBudgetMode('CUSTOM')}
                />
                <span>
                  <strong>예산 직접 설정</strong>
                  <small>참가자 한 명당 사용할 금액</small>
                </span>
              </label>
            </div>
            <label className="contest-budget-amount">
              1인당 금액 · 원
              <input
                name="personalBudgetKrw"
                type="number"
                min={1}
                max={1000000000000}
                step={1}
                required={budgetMode === 'CUSTOM'}
                disabled={budgetMode === 'DEFAULT'}
                value={
                  budgetMode === 'DEFAULT' ? (catalog.defaultPersonalBudgetKrw ?? '') : customBudget
                }
                onChange={(event) => setCustomBudget(event.target.value)}
                placeholder="금액 입력"
                aria-describedby="contest-budget-value"
              />
              <span id="contest-budget-value" className="contest-selection-hint">
                {budgetMode === 'CUSTOM' && customBudget && Number.isFinite(Number(customBudget))
                  ? won(Number(customBudget))
                  : budgetMode === 'CUSTOM'
                    ? '1원 ~ 1조 원'
                    : '기본 예산이 모든 참가자에게 적용됩니다.'}
              </span>
            </label>
            <p className="contest-note">
              모든 참가자에게 같은 금액을 적용합니다. 일반 게임·다른 대회의 예산과 별도로 사용하며
              공개 후에는 변경할 수 없습니다.
            </p>
          </fieldset>
          <fieldset>
            <legend>대회 맵</legend>
            <CompetitionDistrictPicker
              districts={catalog.districts}
              selected={districts}
              onChange={setDistricts}
              disabled={busy}
            />
          </fieldset>
          <fieldset>
            <legend>설치 가능 시설</legend>
            <CompetitionFacilityPicker
              types={catalog.facilityTypes}
              selected={types}
              onChange={setTypes}
              disabled={busy}
            />
          </fieldset>
          <div className="contest-form-grid">
            <label>
              시작 · 한국 시간
              <input
                type="datetime-local"
                name="opensAt"
                required
                defaultValue={kstInput(now + 3600000)}
              />
            </label>
            <label>
              종료 · 한국 시간
              <input
                type="datetime-local"
                name="closesAt"
                required
                defaultValue={kstInput(now + 7 * 86400000)}
              />
            </label>
          </div>
          <fieldset>
            <legend>시상 규모 · 총 {won(total)}</legend>
            <p>
              상금 없이 상만 등록할 수도 있습니다. 같은 점수의 공동 순위 처리 기준을 시상 안내에
              적어 주세요.
            </p>
            {awards.map((a) => (
              <div className="contest-award-row" key={a.key}>
                <label>
                  상 이름
                  <input
                    required
                    maxLength={80}
                    value={a.title}
                    onChange={(e) => changeAward(a.key, 'title', e.target.value)}
                  />
                </label>
                <label>
                  시작 순위
                  <input
                    type="number"
                    min={1}
                    max={1000}
                    required
                    value={a.rankFrom}
                    onChange={(e) => changeAward(a.key, 'rankFrom', e.target.value)}
                  />
                </label>
                <label>
                  끝 순위
                  <input
                    type="number"
                    min={1}
                    max={1000}
                    required
                    value={a.rankTo}
                    onChange={(e) => changeAward(a.key, 'rankTo', e.target.value)}
                  />
                </label>
                <label>
                  1인 상금 · 원
                  <input
                    type="number"
                    min={0}
                    max={1000000000}
                    required
                    value={a.prizeKrw}
                    onChange={(e) => changeAward(a.key, 'prizeKrw', e.target.value)}
                  />
                </label>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`${a.title || '시상 항목'} 삭제`}
                  onClick={() => setAwards((v) => v.filter((x) => x.key !== a.key))}
                >
                  <X size={18} />
                </button>
              </div>
            ))}
            <button
              type="button"
              className="outline-button"
              disabled={awards.length >= 20}
              onClick={() =>
                setAwards((v) => [
                  ...v,
                  {
                    key: crypto.randomUUID(),
                    title: '',
                    rankFrom: (v.at(-1)?.rankTo ?? 0) + 1,
                    rankTo: (v.at(-1)?.rankTo ?? 0) + 1,
                    prizeKrw: 0,
                  },
                ])
              }
            >
              <Plus size={16} />
              시상 항목 추가
            </button>
          </fieldset>
          <label>
            시상 및 운영 안내
            <textarea
              name="awardNotice"
              required={awards.length > 0}
              minLength={awards.length ? 10 : undefined}
              maxLength={2000}
              rows={3}
              placeholder="시상 대상, 공동 순위, 지급 일정·방법 및 문의처"
            />
          </label>
          <label className="contest-check">
            <input type="checkbox" required />
            모드·맵·시설·예산·기간·시상 조건을 확인했으며, 이 조건으로 대회를 공개합니다.
          </label>
          {error && (
            <p role="alert" className="contest-error">
              {error}
            </p>
          )}
          <button type="submit" className="solid-button" disabled={busy}>
            {busy ? '공개 중…' : '대회 공개하기'}
          </button>
        </fieldset>
      </form>
    </section>
  );
}
