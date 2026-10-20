import { memo, useMemo } from 'react';
import type { FacilityType } from '../../game/entity/game';
import {
  candidateKey,
  candidateMatches,
  type GroundCandidate,
} from '../service/candidateTilesService';
import { availableSiteColor } from '../../city/service/siteVisibilityService';
export const GroundCandidatesPlan = memo(function GroundCandidatesPlan({
  rows,
  type,
  ownDistrictId,
  occupiedSites,
  onSelect,
}: {
  rows: GroundCandidate[];
  occupiedSites: ReadonlySet<string>;
  type: FacilityType | '';
  ownDistrictId: string | null;
  onSelect: (key: string) => void;
}) {
  const paths = useMemo(
    () =>
      rows.map((row) => ({
        row,
        d: row[3]
          .flat()
          .map((ring) => ring.map(([x, y], i) => `${i ? 'L' : 'M'}${x},${-y}`).join(' ') + 'Z')
          .join(' '),
      })),
    [rows]
  );
  return (
    <g aria-label="지상 설치 가능 구역">
      {paths.map(({ row, d }) => {
        const matches = candidateMatches(row, type) && !occupiedSites.has(candidateKey(row));
        return (
          <path
            key={candidateKey(row)}
            data-map-cursor={occupiedSites.has(candidateKey(row)) ? 'inspect' : 'install'}
            data-ground-candidate={candidateKey(row)}
            d={d}
            fillRule="evenodd"
            pointerEvents={row[0].startsWith('overview-') ? 'none' : undefined}
            fill={matches ? availableSiteColor : '#9caaa1'}
            fillOpacity={0.7}
            opacity={(matches ? 1 : 0.2) * (ownDistrictId && row[1] !== ownDistrictId ? 0.16 : 1)}
            onClick={(e) => {
              e.stopPropagation();
              onSelect(candidateKey(row));
            }}
          />
        );
      })}
    </g>
  );
});
