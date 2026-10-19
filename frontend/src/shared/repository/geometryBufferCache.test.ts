import { expect, test } from 'vitest';
import { GeometryBufferCache } from './geometryBufferCache';
test('형상 버퍼 상한과 최근 사용 순서, 지형·표시 변경의 캐시 분리', () => {
  const cache = new GeometryBufferCache<{ positions: Float32Array }>(24),
    a = {},
    b = {},
    c = {};
  const value = () => ({ positions: new Float32Array(3) }),
    first = value(),
    second = value();
  cache.put(a, 'terrain1', first);
  cache.put(b, 'terrain1', second);
  expect(cache.get(a, 'terrain1')).toBe(first);
  cache.put(c, 'terrain1', value());
  expect(cache.get(b, 'terrain1')).toBeUndefined();
  expect(cache.get(a, 'terrain1')).toBe(first);
  expect(cache.get(a, 'terrain2')).toBeUndefined();
  cache.put(a, 'terrain2', value());
  expect(cache.get(a, 'terrain1')).toBeUndefined();
  cache.put({}, 'large', { positions: new Float32Array(100) });
  expect(cache.get(c, 'terrain1')).toBeDefined();
});
