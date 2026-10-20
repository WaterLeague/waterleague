import type { InfrastructureAsset } from '../entity/infrastructure';
import type { PlanView } from '../../city/service/planNavigationService';
import { siteFocus } from '../../city/service/siteFocusService';
export function infrastructureFocus(
  asset: InfrastructureAsset,
  width: number,
  height: number,
  current: PlanView
): PlanView {
  const footprint = asset.footprint;
  const fitted = footprint
    ? siteFocus(
        {
          polygons: footprint.polygons,
          kind: footprint.buildingId ? 'ROOF' : 'GROUND',
          heightM: footprint.displayHeightM ?? 0,
        },
        width,
        height,
        45
      )
    : { center: asset.center, distance: 55, heightM: 3 };
  // 목록과 지도 선택 모두 중심을 이동하며, 충분히 가까운 배율은 보존한다.
  return { ...fitted, distance: Math.min(current.distance, fitted.distance) };
}
