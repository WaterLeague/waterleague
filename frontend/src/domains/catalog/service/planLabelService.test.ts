import { describe, expect, it } from 'vitest';
import { positionPlanLabels } from './planLabelService';

describe('평면도 구역 표식', () => {
  it('서로 떨어진 구역의 표식을 원래 중심에 유지한다', () => {
    expect(
      positionPlanLabels(
        [
          [-50, 40],
          [50, -40],
        ],
        1,
        300,
        300
      )
    ).toEqual([
      [-50, 40],
      [50, -40],
    ]);
  });

  it('좁은 화면에서 겹친 표식을 구역 순서와 경계 안에서 분리한다', () => {
    const centers: [number, number][] = [
      [-40, 40],
      [-32, 35],
      [0, 0],
      [0, 0],
      [130, 130],
    ];
    const positions = positionPlanLabels(centers, 0.8, 300, 300);
    expect(positions).toEqual(positionPlanLabels(centers, 0.8, 300, 300));
    for (const [index, [east, north]] of positions.entries()) {
      expect(Math.abs(east) + 18 / 0.8).toBeLessThanOrEqual(150);
      expect(Math.abs(north) + 14 / 0.8).toBeLessThanOrEqual(150);
      for (const [otherEast, otherNorth] of positions.slice(0, index))
        expect(
          Math.abs(east - otherEast) >= 36 / 0.8 || Math.abs(north - otherNorth) >= 28 / 0.8
        ).toBe(true);
    }
    expect(centers[1]).toEqual([-32, 35]);
  });
});
