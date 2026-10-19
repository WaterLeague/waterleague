import type { SharedInstallation } from '../entity/installation';
import { siteKey } from '../entity/installation';
import { facilitySymbolPaths } from '../../catalog/service/facilitySymbolService';
import { facilities } from '../../game/service/gameService';
import { buildingOpacity } from '../../city/service/siteVisibilityService';
import { installationScore } from '../service/installationScore';

import type { FacilityType } from '../../game/entity/game';

export function InstallationSymbolsPlan({
  facilityType = '',
  installations,
  selectedKey,
  ownDistrictId,
  scale,
  onSelect,
}: {
  facilityType?: FacilityType | '';
  installations: SharedInstallation[];
  selectedKey: string;
  ownDistrictId: string | null;
  scale: number;
  onSelect: (key: string) => void;
}) {
  return (
    <g aria-label="사용자 시설 형태 기호">
      {installations.map((i) => (
        <g
          key={i.id}
          transform={`translate(${i.center[0]} ${-i.center[1]}) scale(${scale})`}
          fill={siteKey(i) === selectedKey ? '#ffd15b' : facilities[i.facilityType].color}
          stroke="#315547"
          strokeWidth={0.12}
          opacity={buildingOpacity(
            !facilityType || i.facilityType === facilityType,
            !!ownDistrictId && i.districtId !== ownDistrictId
          )}
          role="button"
          tabIndex={0}
          aria-label={`${i.ownerName} · ${facilities[i.facilityType].name} 위치 보기`}
          onClick={(event) => {
            event.stopPropagation();
            onSelect(siteKey(i));
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              event.stopPropagation();
              onSelect(siteKey(i));
            }
          }}
        >
          <title>{`${i.ownerName} · ${facilities[i.facilityType].name} · ${installationScore(i)} · 종류 기호, 실제 치수 아님`}</title>
          {facilitySymbolPaths[i.facilityType].map((path, index) => (
            <path key={path} d={path} fill={index ? 'none' : undefined} />
          ))}
        </g>
      ))}
    </g>
  );
}
