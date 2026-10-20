import type { PointModelKind } from '../service/pointModelService';
import type { TopographyIndex } from '../dto/topographyDto';
export type TopographyView = {
  index: TopographyIndex | null;
  tiles: { id: string; data: TopographyBuffers }[];
};
export type TopographyBuffers = {
  models: { kind: PointModelKind; cell: [number, number]; matrices: Float32Array }[];
  positions: Float32Array;
  colors: Float32Array;
  normals: Float32Array;
  lines: Float32Array;
  lineColors: Float32Array;
  plan: { layer: number; areas: string; lines: string; points: string }[];
  labels: { point: [number, number]; text: string; layer: number }[];
  counts: { points: number; lines: number; areas: number };
};
