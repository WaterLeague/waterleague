import { expect, it } from 'vitest';
import { sameMapModels } from './modelFamilyService';
import { rainfallCatalogDto } from '../dto/labDto';
import oldModel from '../../../../../data/models/seongsu-lab.json';
import newModel from '../../../../../data/models/seongsu-ngii-v2-421-20240718.json';
it('같은 셀 이름이어도 서로 다른 공간 모델은 배치 비교에서 제외', () => {
  const catalog = rainfallCatalogDto.parse({
    defaultModelHash: 'a'.repeat(64),
    models: [oldModel, newModel].map((m, i) => ({
      modelHash: (i ? 'b' : 'a').repeat(64),
      title: m.title,
      budget: m.budget,
      mapId: i ? 'new' : 'old',
      validationLevel: 'EXPLORATORY',
      official: false,
      rainfall: m.rainfall,
    })),
  });
  expect(sameMapModels(catalog, 'a'.repeat(64)).map((m) => m.mapId)).toEqual(['old']);
  expect(sameMapModels(catalog, 'b'.repeat(64)).map((m) => m.mapId)).toEqual(['new']);
  expect(sameMapModels(catalog, 'unknown')).toEqual([]);
});
