import { describe, expect, it } from 'vitest';
import { positionDistrictLabels } from './districtLabelService';
import type { LabelBounds, SceneLabel } from '../../catalog/service/sceneLabelService';

function verify(labels: SceneLabel[], bounds: LabelBounds) {
  const result = positionDistrictLabels(labels, bounds);
  expect(result.map((v) => v.id).sort()).toEqual(labels.map((v) => v.id).sort());
  for (const [i, label] of result.entries()) {
    expect(label.x - label.width / 2).toBeGreaterThanOrEqual(bounds.left);
    expect(label.x + label.width / 2).toBeLessThanOrEqual(bounds.right);
    expect(label.y - label.height / 2).toBeGreaterThanOrEqual(bounds.top);
    expect(label.y + label.height / 2).toBeLessThanOrEqual(bounds.bottom);
    for (const other of result.slice(0, i))
      expect(
        Math.abs(label.x - other.x) >= (label.width + other.width) / 2 + 4 ||
          Math.abs(label.y - other.y) >= (label.height + other.height) / 2 + 4
      ).toBe(true);
  }
}

describe('활성 자치구 전체 라벨', () => {
  const labels = Array.from({ length: 25 }, (_, i) => ({
    id: `district-${i}`,
    x: 620 + (i % 3),
    y: 150 + (i % 5),
    width: 172,
    height: 44,
    priority: 0,
  }));
  it('북쪽에 라벨이 몰려도 25개를 생략하지 않고 화면 안에 배치', () => {
    verify(labels, { left: 12, top: 130, right: 1268, bottom: 460 });
  });
  it('좁은 화면에서 이름 표식 25개를 모두 유지', () => {
    verify(
      labels.map((v) => ({ ...v, width: 80, height: 30 })),
      { left: 12, top: 130, right: 468, bottom: 460 }
    );
  });
  it('일부 구 대회는 활성 구만 배치', () => {
    verify(labels.slice(0, 3), { left: 12, top: 130, right: 1268, bottom: 460 });
  });
});
