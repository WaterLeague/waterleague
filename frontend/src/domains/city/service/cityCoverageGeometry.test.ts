import source from '../../../../public/data/seoul-coverage-v1.json';
import { expect, test } from 'vitest';
import { cityCoverageDto } from '../repository/cityCoverageRepository';
import { cityCoverageGeometry } from './cityCoverageGeometry';

test('원 피복 검사와 같은 미지원 면적을 유지하고 지원 구멍을 채우지 않음', () => {
  const data = cityCoverageDto.parse(source);
  expect(
    data.areas.filter((a) => a.status === 'UNSUPPORTED').reduce((sum, a) => sum + a.areaM2, 0)
  ).toBeCloseTo(37641214.56263838, 3);
  const area = {
    ...data.areas[0],
    polygons: [
      [
        [
          [0, 0],
          [10, 0],
          [10, 10],
          [0, 10],
          [0, 0],
        ],
        [
          [2, 2],
          [2, 4],
          [4, 4],
          [4, 2],
          [2, 2],
        ],
      ],
    ] as [number, number][][][],
  };
  const geometry = cityCoverageGeometry([area], null);
  const p = geometry.getAttribute('position');
  let covered = 0;
  for (let i = 0; i < p.count; i += 3) {
    const ax = p.getX(i),
      az = p.getZ(i),
      bx = p.getX(i + 1),
      bz = p.getZ(i + 1),
      cx = p.getX(i + 2),
      cz = p.getZ(i + 2);
    covered += Math.abs((bx - ax) * (cz - az) - (bz - az) * (cx - ax)) / 2;
    expect(p.getY(i)).toBeCloseTo(0.6);
  }
  expect(covered).toBeCloseTo(96);
  geometry.dispose();
});
