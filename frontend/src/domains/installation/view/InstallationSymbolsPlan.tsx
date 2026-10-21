import type { SharedInstallation } from '../entity/installation';
import { siteKey } from '../entity/installation';
import { facilityIcons } from '../../facility/view/facilityIcons';
import { facilities } from '../../game/service/gameService';
import { buildingOpacity } from '../../city/service/siteVisibilityService';
import { installationScore } from '../service/installationScore';

import type { FacilityType } from '../../game/entity/game';

export function InstallationSymbolsPlan({
  facilityType = '',
  installations,
  selectedKey,
  ownDistrictId,
  viewerId,
  scale,
  onSelect,
}: {
  facilityType?: FacilityType | '';
  installations: SharedInstallation[];
  selectedKey: string;
  ownDistrictId: string | null;
  viewerId: string | null;
  scale: number;
  onSelect: (key: string) => void;
}) {
  return (
    <g aria-label="사용자 시설 형태 기호">
      {installations.map((i) => {
        const Icon = facilityIcons[i.facilityType];
        return (
          <g
            data-map-cursor="inspect"
            key={i.id}
            transform={`translate(${i.center[0]} ${-i.center[1]}) scale(${scale})`}
            color={
              siteKey(i) === selectedKey
                ? '#ffdc73'
                : i.ownerId === viewerId
                  ? '#71ffe0'
                  : '#ffffff'
            }
            stroke="#315547"
            strokeWidth={0.12}
            opacity={Math.max(
              0.72,
              buildingOpacity(
                !facilityType || i.facilityType === facilityType,
                !!ownDistrictId && i.districtId !== ownDistrictId
              )
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
            <circle r={1.3} fill="#153e3e" stroke="currentColor" strokeWidth={0.16} />
            <Icon x={-1} y={-1} width={2} height={2} strokeWidth={2} />
          </g>
        );
      })}
    </g>
  );
}
