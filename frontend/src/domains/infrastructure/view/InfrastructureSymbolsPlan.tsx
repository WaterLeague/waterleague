import type { InfrastructureAsset } from '../entity/infrastructure';
import { infrastructureColor, infrastructureMarkers } from '../service/infrastructureService';
export function InfrastructureSymbolsPlan({
  assets,
  selectedId,
  scale,
  onSelect,
  distance,
}: {
  assets: InfrastructureAsset[];
  selectedId: string;
  scale: number;
  onSelect: (asset: InfrastructureAsset) => void;
  distance: number;
}) {
  return (
    <g aria-label="공개 시설 형태 기호">
      {infrastructureMarkers(assets, distance, selectedId).map((asset) => (
        <g
          data-map-cursor="inspect"
          key={asset.id}
          transform={`translate(${asset.center[0]} ${-asset.center[1]}) scale(${scale})`}
          fill={asset.id === selectedId ? '#dda62e' : infrastructureColor(asset)}
          stroke="#edf4f2"
          strokeWidth={0.13}
          role="button"
          tabIndex={0}
          aria-label={
            asset.clusterCount && asset.clusterCount > 1
              ? `공개 시설 ${asset.clusterCount}개 · 확대해서 보기`
              : `${asset.name} 공개 시설`
          }
          onClick={(e) => {
            e.stopPropagation();
            onSelect(asset);
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              onSelect(asset);
            }
          }}
        >
          <title>{asset.name} · 시설 종류 기호, 실제 치수 아님</title>
          {(asset.clusterCount ?? 0) > 1 && (
            <text
              y="-1.2"
              textAnchor="middle"
              fill="#46266a"
              stroke="none"
              fontSize="1.3"
              fontWeight="800"
            >
              {asset.clusterCount}
            </text>
          )}
          {asset.kind === 'STORM_PUMP' ? (
            <>
              <path d="M-1 .8 V-.6 H.1 V.8 Z M.1 .1 H.9 V-.8 H.5 V-.3 H.1 Z" />
              <circle cx="-.45" cy=".15" r=".22" fill="#b7dfe9" />
            </>
          ) : asset.kind === 'RAINWATER_REUSE' ? (
            <>
              <path d="M-.7 -.6 V.6 Q0 1 .7 .6 V-.6 Z" />
              <ellipse cx="0" cy="-.6" rx=".7" ry=".25" />
            </>
          ) : asset.kind === 'INFILTRATION_GUTTER' ||
            asset.kind === 'INFILTRATION_TRENCH' ||
            asset.kind === 'INFILTRATION_PIT' ? (
            <>
              <rect
                x="-1"
                y="-.5"
                width="2"
                height="1"
                rx={asset.kind === 'INFILTRATION_PIT' ? 0.5 : 0.1}
              />
              <path d="M-.6 -.4 V.4 M-.2 -.4 V.4 M.2 -.4 V.4 M.6 -.4 V.4" fill="none" />
            </>
          ) : (
            <>
              <path d="M-1 .6 L-.7 -.6 H.7 L1 .6 Z" />
              <path d="M-.5 .3 Q0 -.1 .5 .3" fill="none" />
              <path d="M-.8 -.4 L-.5 -1 L-.2 -.4 Z" fill="#5b825d" />
            </>
          )}
        </g>
      ))}
    </g>
  );
}
