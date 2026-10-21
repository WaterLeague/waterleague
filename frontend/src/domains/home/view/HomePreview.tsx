import { lazy, Suspense, useState } from 'react';
import { Box, RotateCcw, RotateCw } from 'lucide-react';
import type { FacilityType } from '../../game/entity/game';
import { ErrorBoundary } from '../../../shared/exception/ErrorBoundary';
import { usePreviewVisibility } from '../controller/usePreviewVisibility';

const HomeScene = lazy(() => import('./HomeScene'));
export function HomePreview({
  mode,
  facility = 'RAIN_GARDEN',
  label,
}: {
  mode?: 'weekly' | 'disaster';
  facility?: FacilityType;
  label: string;
}) {
  const { ref, visible } = usePreviewVisibility();
  const [angle, setAngle] = useState(0);
  const fallback = (
    <div className="home-preview-fallback">
      <Box size={30} />
      <span>{label}</span>
      <small>아래 설명에서 시설과 게임 방법을 확인하세요.</small>
    </div>
  );
  return (
    <div
      className={`home-preview${mode ? ` is-${mode}` : ''}`}
      ref={ref}
      role="group"
      aria-label={`${label} 3D 미리보기`}
    >
      <span className="home-preview-label">3D 미리보기</span>
      {visible && (
        <ErrorBoundary fallback={fallback}>
          <Suspense
            fallback={
              <div className="home-preview-fallback" role="status">
                3D 모형을 불러오는 중
              </div>
            }
          >
            <HomeScene mode={mode} facility={facility} angle={angle} />
          </Suspense>
        </ErrorBoundary>
      )}
      <div className="home-preview-controls">
        <span>드래그해서 돌려보세요</span>
        <button
          type="button"
          aria-label={`${label} 왼쪽으로 회전`}
          onClick={() => setAngle((a) => a - Math.PI / 4)}
        >
          <RotateCcw size={15} />
        </button>
        <button
          type="button"
          aria-label={`${label} 오른쪽으로 회전`}
          onClick={() => setAngle((a) => a + Math.PI / 4)}
        >
          <RotateCw size={15} />
        </button>
      </div>
    </div>
  );
}
