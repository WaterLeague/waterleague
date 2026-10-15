import { describe, expect, it } from 'vitest';
import model from '../../../../../data/models/seongsu-lab.json';
import { mapLab } from './labMapper';
const lab = () => ({ modelHash: 'a'.repeat(64), model: structuredClone(model) });
describe('실험 계약', () => {
  it('실제 커밋 자료의 원화·시간·면적 계약 수용', () => {
    expect(mapLab(lab()).model.currency).toBe('KRW');
  });
  it('단위 변경과 강우 결측·총량 불일치 거부', () => {
    const a = lab();
    a.model.currency = 'POINT';
    expect(() => mapLab(a)).toThrow();
    const b = lab();
    b.model.rainfall.depthsMm.pop();
    expect(() => mapLab(b)).toThrow();
    const c = lab();
    c.model.rainfall.totalDepthMm += 1;
    expect(() => mapLab(c)).toThrow();
  });
  it('중복 구역·면적 초과 거부', () => {
    const a = lab();
    a.model.cells.push(a.model.cells[0]);
    expect(() => mapLab(a)).toThrow();
    const b = lab();
    b.model.cells[0].maxAreaM2 = b.model.cells[0].areaM2 + 1;
    expect(() => mapLab(b)).toThrow();
  });
});

it('카탈로그의 중복 해시·기본 모델 누락 거부', async () => {
  const { mapRainfallCatalog } = await import('./labMapper');
  const entry = {
    modelHash: 'a'.repeat(64),
    title: model.title,
    budget: model.budget,
    validationLevel: 'EXPLORATORY',
    official: false,
    rainfall: model.rainfall,
  };
  expect(
    mapRainfallCatalog({ defaultModelHash: entry.modelHash, models: [entry] }).models
  ).toHaveLength(1);
  expect(() =>
    mapRainfallCatalog({ defaultModelHash: entry.modelHash, models: [entry, entry] })
  ).toThrow();
  expect(() => mapRainfallCatalog({ defaultModelHash: 'b'.repeat(64), models: [entry] })).toThrow();
});
