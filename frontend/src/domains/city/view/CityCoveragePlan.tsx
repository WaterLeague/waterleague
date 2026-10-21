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
