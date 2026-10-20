import { afterEach, expect, test, vi } from 'vitest';
import actual from '../__tests__/fixtures/nativeBoundarySite.json';
import { loadGroundSite } from './installationRepository';

afterEach(() => vi.unstubAllGlobals());

test('클릭 좌표만 조회하고 소속 구는 서버의 원형 후보에서 수신', async () => {
  const fetcher = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(actual)));
  vi.stubGlobal('fetch', fetcher);
  const site = await loadGroundSite([13281.03424519865, -4865.481269954937]);
  expect(fetcher.mock.calls[0][0]).toBe(
    '/api/v1/installations/sites/ground?x=13281.03424519865&y=-4865.481269954937'
  );
  expect(site.districtId).toBe(actual.districtId);
  expect(site.polygons).toEqual(actual.polygons);
});
