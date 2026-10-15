import { lazy, Suspense, useCallback, useMemo, useState } from 'react';
import { Box, RotateCcw, Scan } from 'lucide-react';
import type { CandidateMap } from '../entity/catalog';
import type { Cell, Placement } from '../../game/entity/game';
import { ErrorBoundary } from '../../../shared/exception/ErrorBoundary';
import { PlanMap } from './PlanMap';

export function MapViewport({
  map,
  cells,
  placements,
  selectedCell,
  onSelect,
}: {
  map: CandidateMap;
  cells: Cell[];
  placements: Placement[];
  selectedCell: string | null;
  onSelect: (id: string | null) => void;
}) {
  const [plan, setPlan] = useState(false);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const MapScene = useMemo(() => lazy(() => import('./MapScene')), [attempt]);
  const [top, setTop] = useState(false);
  const [reset, setReset] = useState(0);
  const unavailable = useCallback(() => setFailed(true), []);
  const isPlan = plan || failed;
  const fallback = (
    <PlanMap
      map={map}
      cells={cells}
      placements={placements}
      selectedCell={selectedCell}
      onCellSelect={onSelect}
    />
  );
  function retry() {
    if (!isPlan) return;
    setAttempt((value) => value + 1);
    setFailed(false);
    setPlan(false);
  }
  return (
    <div className={`map-viewport${failed ? ' map-unavailable' : ''}`}>
      {isPlan ? (
        fallback
      ) : (
        <ErrorBoundary key={attempt} fallback={fallback} onError={unavailable}>
          <Suspense
            fallback={
              <div className="empty-state" role="status">
                3D 장면 구성 중
              </div>
            }
          >
            <MapScene
              map={map}
              selected={cells.find((cell) => cell.id === selectedCell)?.buildingId ?? null}
              onSelect={onSelect}
              topView={top}
              reset={reset}
              cells={cells}
              placements={placements}
              selectedCell={selectedCell}
              onCellSelect={onSelect}
              onUnavailable={unavailable}
            />
          </Suspense>
        </ErrorBoundary>
      )}
      <div className="map-display-options" role="group" aria-label="지도 표시 방식">
        <button aria-pressed={!isPlan} onClick={retry}>
          {failed ? '3D 다시 시도' : '3D'}
        </button>
        <button aria-pressed={isPlan} onClick={() => setPlan(true)}>
          2D 평면도
        </button>
      </div>
      {failed && (
        <p className="map-feedback" role="status">
          3D 그래픽 연결을 사용할 수 없어 평면도로 전환했습니다. 현재 설계는 유지됩니다.
        </p>
      )}
      <div className={`scene-labels${isPlan ? ' plan-labels' : ''}`}>
        {!isPlan && (
          <b>
            SEONGSU
            <br />
            <span>RAIN LAB</span>
          </b>
        )}
        <small>
          {isPlan ? (
            <>
              구역 선택 · 클릭
              <br />
              키보드 · Tab, Enter
            </>
          ) : (
            <>
              회전 · 드래그
              <br />
              확대 · 스크롤
            </>
          )}
        </small>
      </div>
      {!isPlan && (
        <div className="scene-controls camera-controls">
          <button
            aria-label={top ? '입체 보기' : '위에서 보기'}
            aria-pressed={top}
            onClick={() => setTop((value) => !value)}
          >
            {top ? <Box size={18} /> : <Scan size={18} />}
          </button>
          <button aria-label="시점 초기화" onClick={() => setReset((value) => value + 1)}>
            <RotateCcw size={17} />
          </button>
        </div>
      )}
      <a className="map-credit" href={map.snapshot.licenseUrl} target="_blank" rel="noreferrer">
        © OpenStreetMap contributors
      </a>
    </div>
  );
}
