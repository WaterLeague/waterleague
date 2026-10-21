import { lazy, Suspense } from 'react';
import { Box } from 'lucide-react';
import type { FacilityType } from '../../game/entity/game';
import { ErrorBoundary } from '../../../shared/exception/ErrorBoundary';
import { usePreviewVisibility } from '../../home/controller/usePreviewVisibility';

const Scene = lazy(() => import('./FacilityThumbnailScene'));

export function FacilityThumbnail({ type }: { type: FacilityType }) {
  const { ref, visible } = usePreviewVisibility();
  const fallback = <Box size={30} />;
  return (
    <div className="contest-facility-preview" ref={ref} aria-hidden="true">
      {visible && (
        <ErrorBoundary fallback={fallback}>
          <Suspense fallback={fallback}>
            <Scene type={type} />
          </Suspense>
        </ErrorBoundary>
      )}
    </div>
  );
}
