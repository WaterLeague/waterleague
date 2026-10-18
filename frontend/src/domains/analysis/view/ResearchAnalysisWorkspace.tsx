import type { ResearchEntry } from '../../research/entity/research';
import { PatternPanel } from './PatternPanel';
import './analysis.css';
import { SearchPanel } from '../../optimization/view/SearchPanel';
import type { Lab } from '../../game/entity/game';
import type { CandidateMap } from '../../catalog/entity/catalog';
export function ResearchAnalysisWorkspace({
  entries,
  lab,
  map,
  organizationId,
  refreshSources,
}: {
  entries: ResearchEntry[];
  lab: Lab;
  map: CandidateMap | null;
  organizationId: string | null;
  refreshSources: () => void;
}) {
  return (
    <section className="institution-analysis" aria-label="기관 연구 분석">
      <div className="page-eyebrow">
        INSTITUTION ANALYSIS <span>EXPLORATORY</span>
      </div>
      <h2>배치 기록과 반복되는 선택을 살핍니다.</h2>
      <p className="analysis-intro">
        현재 동의된 제출 기록을 대상으로 합니다. 재계산과 배치 빈도는 현장 효과를 검증한 결과가
        아닙니다.
      </p>
      <PatternPanel entries={entries} />
      {organizationId && (
        <SearchPanel
          lab={lab}
          map={map}
          organizationId={organizationId}
          entries={entries}
          refreshSources={refreshSources}
        />
      )}
    </section>
  );
}
