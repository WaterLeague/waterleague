import { memo } from 'react';
import type { TraceTile } from '../entity/floodTrace';
import { traceColor } from '../service/floodTraceService';

export const FloodTracePlan = memo(function FloodTracePlan({ tiles }: { tiles: TraceTile[] }) {
  return (
    <g pointerEvents="none" fill={traceColor} opacity={0.48} fillRule="evenodd">
      {tiles.map((t) => (
        <path key={`${t.eventId}/${t.id}`} d={t.path} />
      ))}
    </g>
  );
});
