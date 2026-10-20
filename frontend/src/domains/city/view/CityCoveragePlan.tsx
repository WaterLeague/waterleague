import { useId } from 'react';
import { polygonPath } from '../../catalog/service/mapGeometryService';
import { useCityCoverage } from '../controller/useCityCoverage';

export function CityCoveragePlan({ distance }: { distance: number }) {
  const { areas } = useCityCoverage(),
    id = useId().replaceAll(':', '');
  const spacing = Math.max(12, Math.min(180, distance / 80));
  return (
    <g pointerEvents="none" aria-label="상세 지도 미지원 영역">
      <defs>
        <pattern
          id={id}
          width={spacing}
          height={spacing}
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(45)"
        >
          <rect width={spacing} height={spacing} fill="#62665c" opacity=".08" />
          <rect width={spacing * 0.14} height={spacing} fill="#62665c" opacity=".4" />
        </pattern>
      </defs>
      {areas.map((area) => (
        <path key={area.id} d={polygonPath(area.polygons)} fill={`url(#${id})`} fillRule="evenodd">
          <title>
            {area.status === 'UNSUPPORTED'
              ? '상세 지도 미지원 · 확보한 수치지형도 범위 밖'
              : '상세 지도 미지원 · 1:5,000 자료만 제공'}
          </title>
        </path>
      ))}
    </g>
  );
}

export function CityCoverageNotice({
  center,
  distance,
}: {
  center: [number, number];
  distance: number;
}) {
  const { areas, failed } = useCityCoverage();
  const radius = Math.max(500, distance);
  const nearby = areas.filter(
    (a) =>
      a.bounds[0] <= center[0] + radius &&
      a.bounds[2] >= center[0] - radius &&
      a.bounds[1] <= center[1] + radius &&
      a.bounds[3] >= center[1] - radius
  );
  if (!failed && !nearby.length) return null;
  return (
    <div className="city-coverage-notice" role="status">
      {failed ? '지도 지원 범위 확인 지연' : '▨ 사선 영역: 상세 지도 미지원'}
      {!failed && <span>확보한 원자료에 없는 지물은 표시하지 않습니다.</span>}
    </div>
  );
}
