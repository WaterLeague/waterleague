import type { SharedSite } from '../../installation/entity/installation';
import type { PlanView } from './planNavigationService';
import { planScale } from './planNavigationService';

export function selectionView(fitted: PlanView, current: PlanView, fromMap = false): PlanView {
  // 가까이서 클릭한 요소는 현재 시야를 보존하고 목록 이동도 기존 확대를 풀지 않는다.
  if (fromMap && current.distance <= fitted.distance) return current;
  return { ...fitted, distance: Math.min(current.distance, fitted.distance) };
}

export function siteFocus(
  site: Pick<SharedSite, 'coordinates' | 'heightM' | 'kind'>,
  width: number,
  height: number,
  minimumDistance = 180
): PlanView {
  const xs = site.coordinates.map(([x]) => x),
    ys = site.coordinates.map(([, y]) => y);
  const west = Math.min(...xs),
    east = Math.max(...xs);
  const south = Math.min(...ys),
    north = Math.max(...ys);
  const center: [number, number] = [(west + east) / 2, (south + north) / 2];
  const roof = site.kind === 'ROOF' ? site.heightM : 0;
  const heightM = roof / 2;
  const aspect = Math.max(0.2, width / Math.max(1, height));
  const horizontal = planScale * aspect * 0.82;
  const vertical = planScale * Math.max(0.35, (height - 240) / height);
  let distance = minimumDistance;
  // 면적 대신 외곽·높이의 모든 꼭짓점을 투영하여 상하 HUD를 제외한 화면에 포함한다.
  for (const x of [west, east])
    for (const y of [south, north])
      for (const z of [0, roof]) {
        const dx = x - center[0],
          dy = z - heightM,
          dz = -(y - center[1]);
        const towards = 0.8 * dy + 0.6 * dz;
        const up = 0.6 * dy - 0.8 * dz;
        distance = Math.max(
          distance,
          towards + Math.abs(dx) / horizontal,
          towards + Math.abs(up) / vertical
        );
      }
  return { center, heightM, distance: Math.min(150000, distance * 1.08) };
}
