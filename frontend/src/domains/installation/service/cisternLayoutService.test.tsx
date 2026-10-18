import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import examples from '../../../../../backend/src/test/resources/cistern-layout-cases.json';
import type { MapPoint } from '../../catalog/entity/facilityFootprint';
import { cisternGeometry, parseCisternLayout } from './cisternLayoutService';
import { CisternLayoutPlan } from '../view/CisternLayoutPlan';
it('서버와 같은 경계·벽체·회전·오목 도형 사례 및 좌표 이동', () => {
  for (const e of examples)
    for (const offset of [0, 203000]) {
      const ground = {
        center: e.center.map((v) => v + offset) as MapPoint,
        coordinates: e.ring.map((p) => p.map((v) => v + offset) as MapPoint),
        modelHash: 'a'.repeat(64),
      };
      const g = cisternGeometry(ground, e.area, e.depth, e.layout)!;
      expect(g.contained, e.name).toBe(e.contained);
      expect(g.internalWidthM * g.internalLengthM).toBeCloseTo(e.area, 8);
      if (e.expected)
        for (let i = 0; i < 5; i++)
          for (let j = 0; j < 2; j++)
            expect(g.coordinates[i][j] - offset).toBeCloseTo(e.expected[i][j], 8);
      expect(
        cisternGeometry(
          { ...ground, coordinates: [...ground.coordinates].reverse() },
          e.area,
          e.depth,
          e.layout
        )
      ).toEqual(g);
    }
});
it('미입력·범위·정밀도 오류 거부와 실제 외곽의 색상 분리', () => {
  const fields = { width: '2', wall: '0.25', east: '1', north: '-0.5', rotation: '0' };
  expect(parseCisternLayout(fields)).toEqual(examples[0].layout);
  for (const changed of [
    { width: '' },
    { wall: '0' },
    { east: '1.0001' },
    { rotation: '360' },
    { width: 'NaN' },
  ])
    expect(parseCisternLayout({ ...fields, ...changed })).toBeNull();
  for (const e of examples.slice(0, 3)) {
    const g = cisternGeometry(
      {
        center: e.center as MapPoint,
        coordinates: e.ring as MapPoint[],
        modelHash: 'a'.repeat(64),
      },
      e.area,
      e.depth,
      e.layout
    )!;
    const html = renderToStaticMarkup(
      <svg>
        <CisternLayoutPlan geometry={g} />
      </svg>
    );
    expect(html).toContain(e.contained ? '#d4a653' : '#d86a55');
    expect(html).toContain('현재 수위 아님');
  }
});
