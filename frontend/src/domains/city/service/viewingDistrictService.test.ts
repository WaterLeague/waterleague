import { expect, it } from 'vitest';
import type { City } from '../entity/city';
import { viewingDistrict } from './viewingDistrictService';
it('시선이 다른 구로 이동하면 조회 구를 바꾸고 구멍과 서울 밖을 제외', () => {
  const districts = [
    {
      id: 'a',
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
            [3, 3],
            [4, 3],
            [4, 4],
            [3, 4],
            [3, 3],
          ],
        ],
      ],
    },
    {
      id: 'b',
      polygons: [
        [
          [
            [10, 0],
            [20, 0],
            [20, 10],
            [10, 10],
            [10, 0],
          ],
        ],
      ],
    },
  ] as City['districts'];
  expect(viewingDistrict(districts, [2, 2])?.id).toBe('a');
  expect(viewingDistrict(districts, [12, 2])?.id).toBe('b');
  expect(viewingDistrict(districts, [3.5, 3.5])).toBeUndefined();
  expect(viewingDistrict(districts, [30, 30])).toBeUndefined();
});
