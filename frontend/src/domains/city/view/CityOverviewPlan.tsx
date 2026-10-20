import { memo, useMemo } from 'react';
import { useCityOverview } from '../controller/useCityOverview';
export const CityOverviewPlan = memo(function CityOverviewPlan({
  center,
  distance,
  detailTileIds,
  ownDistrictId,
}: {
  center: [number, number];
  distance: number;
  detailTileIds: ReadonlySet<string>;
  ownDistrictId: string | null;
}) {
  const { data, visible, failed } = useCityOverview(center, distance, detailTileIds);
  const paths = useMemo(() => {
    const groups = new Map<number, string[]>();
    for (const [x, y, width, depth, , district] of visible) {
      let parts = groups.get(district);
      if (!parts) {
        parts = [];
        groups.set(district, parts);
      }
      parts.push(
        `M${(x - width / 2).toFixed(2)},${(-y - depth / 2).toFixed(2)}h${width}v${depth}h${-width}Z`
      );
    }
    return [...groups].map(([district, parts]) => ({ district, path: parts.join('') }));
  }, [visible]);
  if (failed) throw new Error('축소 지도 표시 실패');
  return (
    <g pointerEvents="none">
      {paths.map(({ district, path }) => (
        <path
          key={district}
          d={path}
          fill={
            ownDistrictId && data?.districts[district] !== ownDistrictId ? '#c4ccbf' : '#d5d7ca'
          }
        />
      ))}
    </g>
  );
});
