import type { RainfallCatalog } from '../../game/entity/game';
import type { ResearchDetail, ResearchEntry } from '../../research/entity/research';
import { ResearchRainfallPanel } from './ResearchRainfallPanel';
import { PatternPanel } from './PatternPanel';
import './analysis.css';
export function ResearchAnalysisWorkspace({
  source,
  entries,
  catalog,
}: {
  source: ResearchDetail | null;
  entries: ResearchEntry[];
  catalog: RainfallCatalog | null;
}) {
  return (
    <section className="institution-analysis" aria-label="기관 연구 분석">
      <div className="page-eyebrow">
        INSTITUTION ANALYSIS <span>EXPLORATORY</span>
      </div>
      <h2>강우를 바꾸고, 반복되는 선택을 살핍니다.</h2>
      <p className="analysis-intro">
        현재 동의된 제출 기록을 대상으로 합니다. 재계산과 배치 빈도는 현장 효과를 검증한 결과가
        아닙니다.
      </p>
      <ResearchRainfallPanel source={source} catalog={catalog} />
      <PatternPanel entries={entries} />
    </section>
  );
}
