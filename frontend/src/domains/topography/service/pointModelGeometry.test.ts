import { expect, test } from 'vitest';
import samples from '../__tests__/fixtures/native-layer-samples-v1.json';
import source from '../../../../public/data/seoul-features-v1/index.json';
import { pointModelKind } from './pointModelService';
import { pointModelGeometry } from './pointModelGeometry';
import { topographyGeometry } from './topographyGeometryService';
import { topographyIndexDto, topographyTileDto } from '../dto/topographyDto';
const index = topographyIndexDto.parse(source),
  tile = topographyTileDto.parse(samples);
test('실물 점 지물은 화면 크기 기호가 아닌 원본 위치의 입체 모형 인스턴스', () => {
  const data = topographyGeometry(tile, index.layers, null, false);
  for (const [layer, , points] of tile.points) {
    const kind = pointModelKind(index.layers[layer].id);
    if (!kind) continue;
    const instances = data.models.filter((m) => m.kind === kind);
    for (const p of points)
      expect(
        instances.some((instance) =>
          Array.from(instance.matrices).some(
            (_, i) =>
              i % 16 === 12 &&
              Math.abs(instance.matrices[i] - p[0]) < 0.004 &&
              Math.abs(instance.matrices[i + 2] + p[1]) < 0.004
          )
        )
      ).toBe(true);
    for (const coarse of [true, false]) {
      const model = pointModelGeometry(kind, coarse),
        geometry = model.geometry;
      geometry.computeBoundingBox();
      const box = geometry.boundingBox!;
      expect(box.max.y - box.min.y, index.layers[layer].id).toBeGreaterThan(0.02);
      expect(box.min.y).toBeGreaterThan(-0.15);
      expect(Array.from(geometry.getAttribute('position').array).every(Number.isFinite)).toBe(true);
      expect(geometry.getAttribute('normal').count).toBe(geometry.getAttribute('position').count);
      expect(pointModelGeometry(kind, coarse)).toBe(model);
    }
  }
  expect(data.models.reduce((n, m) => n + m.matrices.length / 16, 0)).toBeGreaterThan(0);
});
test('야간 발광은 원본 위치 조명 모형의 등기구에만 결속', () => {
  const lamp = pointModelGeometry('LAMP', false);
  const mask = lamp.geometry.getAttribute('sourceLamp'),
    positions = lamp.geometry.getAttribute('position');
  let emitting = 0;
  for (let i = 0; i < mask.count; i++)
    if (mask.getX(i)) {
      expect(positions.getY(i)).toBeGreaterThan(6);
      emitting++;
    }
  expect(emitting).toBeGreaterThan(0);
  expect(emitting).toBeLessThan(mask.count);
  expect(
    [...pointModelGeometry('UTILITY_POLE', false).geometry.getAttribute('sourceLamp').array].every(
      (v) => v === 0
    )
  ).toBe(true);
});
