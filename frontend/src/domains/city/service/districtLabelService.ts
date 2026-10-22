import {
  positionSceneLabels,
  type LabelBounds,
  type SceneLabel,
} from '../../catalog/service/sceneLabelService';

export function positionDistrictLabels(labels: SceneLabel[], bounds: LabelBounds): SceneLabel[] {
  const ordered = [...labels].sort((a, b) => a.y - b.y || a.x - b.x || a.id.localeCompare(b.id));
  const local = positionSceneLabels(
    ordered.map((v, i) => ({ ...v, priority: -i })),
    bounds
  );
  if (local.length === labels.length) return local;
  const placedIds = new Set(local.map((v) => v.id));
  for (const label of ordered.filter((v) => !placedIds.has(v.id))) {
    const xs = [bounds.left + label.width / 2, bounds.right - label.width / 2, label.x];
    const ys = [bounds.top + label.height / 2, bounds.bottom - label.height / 2, label.y];
    for (const other of local) {
      xs.push(
        other.x - (other.width + label.width) / 2 - 6,
        other.x + (other.width + label.width) / 2 + 6
      );
      ys.push(
        other.y - (other.height + label.height) / 2 - 6,
        other.y + (other.height + label.height) / 2 + 6
      );
    }
    let closest: SceneLabel | null = null;
    let distance = Infinity;
    for (const x of xs)
      for (const y of ys) {
        if (
          x - label.width / 2 < bounds.left ||
          x + label.width / 2 > bounds.right ||
          y - label.height / 2 < bounds.top ||
          y + label.height / 2 > bounds.bottom
        )
          continue;
        const delta = Math.hypot(x - label.x, y - label.y);
        if (
          delta >= distance ||
          local.some(
            (v) =>
              Math.abs(x - v.x) < (label.width + v.width) / 2 + 4 &&
              Math.abs(y - v.y) < (label.height + v.height) / 2 + 4
          )
        )
          continue;
        closest = { ...label, x, y };
        distance = delta;
      }
    if (closest) local.push(closest);
  }
  if (local.length === labels.length) return local;
  const width = Math.max(...labels.map((v) => v.width)) + 6;
  const height = Math.max(...labels.map((v) => v.height)) + 6;
  const columns = Math.floor((bounds.right - bounds.left) / width);
  const rows = Math.floor((bounds.bottom - bounds.top) / height);
  if (!columns || !rows || columns * rows < labels.length) return [];
  // 밀집 화면에서는 남북·동서 순서를 유지한 행에 전체 표식을 배치한다.
  const usedRows = Math.ceil(labels.length / columns);
  return Array.from({ length: usedRows }, (_, row) => {
    const entries = ordered
      .slice(
        Math.floor((row * labels.length) / usedRows),
        Math.floor(((row + 1) * labels.length) / usedRows)
      )
      .sort((a, b) => a.x - b.x);
    return entries.map((label, column) => ({
      ...label,
      x: bounds.left + ((column + 0.5) * (bounds.right - bounds.left)) / entries.length,
      y: bounds.top + ((row + 0.5) * (bounds.bottom - bounds.top)) / usedRows,
    }));
  }).flat();
}
