import { useState } from 'react';
import { Play, RefreshCw } from 'lucide-react';
import type { Lab } from '../../game/entity/game';
import type { CandidateMap } from '../../catalog/entity/catalog';
import type { ResearchEntry } from '../../research/entity/research';
import { useSearch } from '../controller/useSearch';
import { searchInputError, searchState } from '../service/searchService';
import type { SearchInput, SearchSettings } from '../entity/search';
import { format, won } from '../../game/service/gameService';
import { SearchResult } from './SearchResult';
import './search.css';
export function SearchPanel({
  lab,
  map,
  organizationId,
  entries,
  refreshSources,
}: {
  lab: Lab;
  map: CandidateMap | null;
  organizationId: string;
  entries: ResearchEntry[];
  refreshSources: () => void;
}) {
  const c = useSearch(lab, organizationId),
    [selected, setSelected] = useState<string[]>([]),
    [settings, setSettings] = useState<SearchSettings>({
      topK: 2,
      budgetKrw: lab.model.budget,
      seed: 17,
      candidatesPerArm: 3,
    });
  const ids = selected.filter((id) => entries.some((e) => e.jobId === id)),
    input: SearchInput = { jobIds: ids, settings };
  const problem = searchInputError(
    input,
    lab.model.budget,
    entries.filter((e) => ids.includes(e.jobId)).map((e) => e.cost)
  );
  function choose(values: string[]) {
    c.invalidate();
    setSelected(values);
  }
  function configure(value: Partial<SearchSettings>) {
    c.invalidate();
    setSettings((s) => ({ ...s, ...value }));
  }
  return (
    <section className="analysis-section candidate-search" aria-label="패턴 기반 후보 탐색">
      <div className="page-heading">
        <div>
          <h3>
            <span className="analysis-step">03</span> 선택을 배우고, 같은 조건에서 비교합니다.
          </h3>
          <p className="analysis-intro">
            상위 배치의 시설·면적 선택 빈도로 새 후보를 만들고 SWMM으로 다시 계산합니다. 같은 예산과
            후보 수의 균등 무작위 대조를 함께 실행합니다.
          </p>
        </div>
      </div>
      <fieldset className="pattern-selection" disabled={c.busy}>
        <legend>후보 생성에 사용할 제출 기록 · {ids.length}/50개</legend>
        <div className="pattern-select-actions">
          <button
            className="text-button"
            disabled={!entries.length}
            onClick={() => choose(entries.slice(0, 50).map((e) => e.jobId))}
          >
            현재 기록 최대 50개 선택
          </button>
          <button className="text-button" disabled={!ids.length} onClick={() => choose([])}>
            표본 선택 해제
          </button>
        </div>
        <div className="pattern-samples">
          {entries.map((e) => (
            <label className="pattern-sample" key={e.jobId}>
              <input
                type="checkbox"
                aria-label={`탐색 표본 ${e.jobId}`}
                checked={ids.includes(e.jobId)}
                disabled={!ids.includes(e.jobId) && ids.length >= 50}
                onChange={(event) =>
                  choose(
                    event.target.checked ? [...ids, e.jobId] : ids.filter((id) => id !== e.jobId)
                  )
                }
              />
              <span>
                <b>
                  {format.format(e.score)}점 · {won(e.cost)}
                </b>
                <small>
                  버전 {e.revision} · 계산 {e.jobId.slice(0, 8)}
                </small>
                <span>{e.designNote || '설계 메모 없음'}</span>
              </span>
            </label>
          ))}
        </div>
        {!entries.length && (
          <p className="empty-state">현재 관측 강우에 동의된 제출 기록이 없습니다.</p>
        )}
        <div className="search-settings">
          <label>
            비교 예산 · 원
            <input
              aria-label="후보 비교 예산 원"
              type="number"
              min={1}
              max={lab.model.budget}
              step={1}
              value={settings.budgetKrw}
              onChange={(e) => configure({ budgetKrw: Number(e.target.value) })}
            />
            <small>모델 한도 {won(lab.model.budget)}</small>
          </label>
          <label>
            상위 고유 배치 기준
            <select
              aria-label="후보 학습 상위 기준"
              value={settings.topK}
              onChange={(e) => configure({ topK: Number(e.target.value) })}
            >
              {Array.from({ length: 19 }, (_, i) => i + 2).map((n) => (
                <option key={n} value={n}>
                  {n}개 + 경계 동점
                </option>
              ))}
            </select>
          </label>
          <label>
            재현 시드
            <input
              aria-label="후보 생성 시드"
              type="number"
              min={0}
              max={2147483647}
              step={1}
              value={settings.seed}
              onChange={(e) => configure({ seed: Number(e.target.value) })}
            />
            <small>같은 표본·조건·시드는 같은 후보 생성</small>
          </label>
          <label>
            방법당 후보 수
            <select
              aria-label="방법당 후보 수"
              value={settings.candidatesPerArm}
              onChange={(e) => configure({ candidatesPerArm: Number(e.target.value) })}
            >
              {[1, 2, 3, 4].map((n) => (
                <option key={n} value={n}>
                  {n}개 · 총 {n * 2}개 계산
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="search-start">
          <button
            className="primary-button"
            disabled={!!problem || c.busy || !lab.model.simulationAvailable}
            onClick={() => c.create(input)}
          >
            <Play size={15} />
            {c.busy ? '요청 처리 중' : `후보 ${settings.candidatesPerArm * 2}개 생성·계산`}
          </button>
          <p>
            {problem || '선택 기록의 물리 중복 제거 후 서로 다른 배치가 2개 이상 필요합니다.'}
            <small>기관의 다강우·후보 계산 합계 9개 이내. 생성 요청은 시간당 6회 이내.</small>
          </p>
        </div>
      </fieldset>
      <div className="search-history">
        <label>
          우리 기관의 후보 탐색 기록 · 현재 강우
          <select
            aria-label="기관 후보 탐색 기록"
            value={c.selectedId}
            disabled={c.busy}
            onChange={(e) => c.open(e.target.value)}
          >
            <option value="">기록 선택</option>
            {c.items.map((item) => (
              <option key={item.id} value={item.id}>
                {new Date(item.createdAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} ·
                시드 {item.settings.seed} · {searchState(item)}
              </option>
            ))}
            {c.detail && !c.items.some((x) => x.id === c.detail?.id) && (
              <option value={c.detail.id}>
                현재 탐색 · 시드 {c.detail.generation.settings.seed}
              </option>
            )}
          </select>
        </label>
        <button
          className="text-button"
          disabled={c.busy}
          onClick={() => {
            c.refresh();
            refreshSources();
          }}
        >
          <RefreshCw size={14} />
          탐색 기록 새로고침
        </button>
      </div>
      {c.error && (
        <p className="form-error" role="alert">
          {c.error}
        </p>
      )}
      {c.busy && <p role="status">현재 권한과 탐색 자료 확인 중</p>}
      {c.detail && <SearchResult key={c.detail.id} detail={c.detail} lab={lab} map={map} />}
    </section>
  );
}
