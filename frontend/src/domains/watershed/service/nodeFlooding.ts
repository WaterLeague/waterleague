import type { NodeFlooding } from '../dto/nodeFloodingDto';
export type FloodView = 'change' | 'baseline' | 'strategy';
export function compareNodeFlooding(baseline: NodeFlooding, strategy: NodeFlooding) {
  const after = new Map(strategy.nodes.map((n) => [n.id, n]));
  return baseline.nodes
    .filter((n) => n.mapped)
    .map((n) => {
      const target = after.get(n.id);
      if (!target || !target.mapped || target.kind !== n.kind)
        throw new Error('절점 월류 비교 불일치');
      return {
        id: n.id,
        kind: n.kind,
        baselineM3: n.floodingM3,
        strategyM3: target.floodingM3,
        reductionM3: n.floodingM3 - target.floodingM3,
        baselineSeconds: n.floodingSeconds ?? null,
        strategySeconds: target.floodingSeconds ?? null,
        reductionSeconds:
          n.floodingSeconds !== undefined && target.floodingSeconds !== undefined
            ? n.floodingSeconds - target.floodingSeconds
            : null,
      };
    });
}
export function floodNodeColor(view: FloodView, value: number, maximum: number) {
  if (value === 0) return '#cad3cf';
  const fraction = maximum > 0 ? Math.min(1, Math.abs(value) / maximum) : 0;
  const level = fraction > 0.5 ? 2 : fraction > 0.1 ? 1 : 0;
  return view === 'change'
    ? (value > 0 ? ['#a2ccbc', '#328c70', '#08654a'] : ['#e7bc9e', '#c57948', '#9e451f'])[level]
    : ['#90c6d9', '#3384ae', '#15537d'][level];
}
