import { describe, expect, it } from 'vitest';
import {
  labelLeaderEnd,
  positionSceneLabels,
  type LabelBounds,
  type SceneLabel,
} from './sceneLabelService';

function verifyVisible(labels: SceneLabel[], bounds: LabelBounds) {
  for (const [index, label] of labels.entries()) {
    expect(label.x - label.width / 2).toBeGreaterThanOrEqual(bounds.left);
    expect(label.x + label.width / 2).toBeLessThanOrEqual(bounds.right);
    expect(label.y - label.height / 2).toBeGreaterThanOrEqual(bounds.top);
    expect(label.y + label.height / 2).toBeLessThanOrEqual(bounds.bottom);
    for (const other of labels.slice(0, index))
      expect(
        Math.abs(label.x - other.x) >= (label.width + other.width) / 2 + 4 ||
          Math.abs(label.y - other.y) >= (label.height + other.height) / 2 + 4
      ).toBe(true);
  }
}

describe('3D 화면 구역 표식', () => {
  it('표시 공간이 부족하면 선택 구역을 우선하고 겹치는 표식은 생략', () => {
    const labels = ['R1', 'G1', 'G2'].map((id) => ({
      id,
      x: 30,
      y: 30,
      width: 40,
      height: 26,
      priority: id === 'G1' ? 3 : 0,
    }));
    const bounds = { left: 0, top: 0, right: 42, bottom: 28 };
    const result = positionSceneLabels(labels, bounds);
    expect(result.map((label) => label.id)).toEqual(['G1']);
    verifyVisible(result, bounds);
    expect(positionSceneLabels(labels, { ...bounds, right: 20 })).toEqual([]);
  });

  it('연결선은 표식의 가장자리에서 끝나며 글자를 가리지 않음', () => {
    const label = { id: 'G1', x: 100, y: 100, width: 40, height: 26, priority: 0 };
    expect(labelLeaderEnd({ x: 100, y: 150 }, label)).toEqual({ x: 100, y: 113 });
    expect(labelLeaderEnd({ x: 180, y: 100 }, label)).toEqual({ x: 120, y: 100 });
    expect(labelLeaderEnd({ x: 100, y: 100 }, label)).toEqual({ x: 100, y: 100 });
  });
});
