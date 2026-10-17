export interface SceneLabel {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  priority: number;
}

export interface LabelBounds {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

const offsets: [number, number][] = [[0, 0]];
for (let radius = 12; radius <= 132; radius += 12)
  for (let angle = 0; angle < 16; angle++) {
    const radians = (angle * Math.PI) / 8;
    offsets.push([Math.cos(radians) * radius, Math.sin(radians) * radius]);
  }

export function positionSceneLabels(labels: SceneLabel[], bounds: LabelBounds): SceneLabel[] {
  const placed: SceneLabel[] = [];
  const ordered = [...labels].sort((a, b) => b.priority - a.priority || a.id.localeCompare(b.id));
  for (const label of ordered) {
    if (label.width > bounds.right - bounds.left || label.height > bounds.bottom - bounds.top)
      continue;
    const center = { x: label.x, y: label.y - label.height / 2 - 8 };
    for (const [dx, dy] of offsets) {
      const x = Math.max(
        bounds.left + label.width / 2,
        Math.min(bounds.right - label.width / 2, center.x + dx)
      );
      const y = Math.max(
        bounds.top + label.height / 2,
        Math.min(bounds.bottom - label.height / 2, center.y + dy)
      );
      if (Math.hypot(x - label.x, y - label.y) > 156) continue;
      if (
        placed.some(
          (other) =>
            Math.abs(x - other.x) < (label.width + other.width) / 2 + 4 &&
            Math.abs(y - other.y) < (label.height + other.height) / 2 + 4
        )
      )
        continue;
      placed.push({ ...label, x, y });
      break;
    }
  }
  return placed;
}

export function labelLeaderEnd(anchor: { x: number; y: number }, label: SceneLabel) {
  const dx = anchor.x - label.x,
    dy = anchor.y - label.y;
  const ratio = Math.max(Math.abs(dx) / (label.width / 2), Math.abs(dy) / (label.height / 2));
  return ratio <= 1 ? anchor : { x: label.x + dx / ratio, y: label.y + dy / ratio };
}
