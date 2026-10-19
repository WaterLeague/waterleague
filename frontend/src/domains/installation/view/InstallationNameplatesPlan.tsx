import { memo, useMemo } from 'react';
import type { SharedInstallation } from '../entity/installation';
import { siteKey } from '../entity/installation';
import { representativeInstallations } from '../service/memberSitesService';
import { installationScore } from '../service/installationScore';
import { positionSceneLabels } from '../../catalog/service/sceneLabelService';
export const InstallationNameplatesPlan = memo(function InstallationNameplatesPlan({
  installations,
  viewerId,
  box,
  onSelect,
}: {
  installations: SharedInstallation[];
  viewerId: string | null;
  box: { x: number; y: number; width: number; height: number };
  onSelect: (key: string) => void;
}) {
  const labels = useMemo(() => {
    const values = [...representativeInstallations(installations, viewerId).values()];
    const aspect = box.width / box.height;
    const candidates = values.flatMap((i) => {
      const x = ((i.center[0] - box.x) / box.height) * 600,
        y = ((-i.center[1] - box.y) / box.height) * 600;
      return x < 0 || x > 600 * aspect || y < 0 || y > 600
        ? []
        : [{ id: i.id, x, y, width: 150, height: 40, priority: i.ownerId === viewerId ? 2 : 0 }];
    });
    return positionSceneLabels(candidates, {
      left: 10,
      top: 65,
      right: 600 * aspect - 10,
      bottom: 510,
    })
      .slice(0, 24)
      .map((label) => ({ ...label, value: values.find((i) => i.id === label.id)! }));
  }, [installations, viewerId, box.x, box.y, box.width, box.height]);
  const scale = box.height / 600;
  return (
    <g aria-label="확대 지도 시설별 점수">
      {labels.map(({ id, x, y, value }) => (
        <g
          data-map-cursor="inspect"
          key={id}
          transform={`translate(${box.x + x * scale} ${box.y + y * scale}) scale(${scale})`}
          role="button"
          tabIndex={0}
          aria-label={`${value.ownerName} · ${installationScore(value)}`}
          onClick={(e) => {
            e.stopPropagation();
            onSelect(siteKey(value));
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              onSelect(siteKey(value));
            }
          }}
        >
          <path
            d={`M0 0 L${(value.center[0] - box.x) / scale - x} ${(-value.center[1] - box.y) / scale - y}`}
            stroke="#a5ffd7"
            strokeWidth={1}
            pointerEvents="none"
          />
          <rect x={-75} y={-20} width={150} height={40} rx={7} fill="#163a31" stroke="#aaffd8" />
          <text x={-65} y={-5} fill="#e8fff4" fontSize={10}>
            {value.ownerId === viewerId ? '내 시설 · ' : ''}
            {value.ownerName.slice(0, 12)}
          </text>
          <text x={-65} y={11} fill="#afffd4" fontSize={12} fontWeight={800}>
            {installationScore(value)}
          </text>
        </g>
      ))}
    </g>
  );
});
