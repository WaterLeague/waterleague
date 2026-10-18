import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { SiteScoreRows } from './SiteScores';
import { siteScoresDto } from '../dto/siteScoresDto';
it('미계산·0·음의 시설 기여를 구별하고 소유자와 계산 시각 표시', () => {
  const value = siteScoresDto.parse({
    installations: [null, 0, -0.125].map((scoreM3, n) => ({
      id: `00000000-0000-4000-8000-00000000000${n}`,
      ownerId: `00000000-0000-4000-8000-00000000000${n}`,
      ownerName: '회원' + n,
      facilityType: 'RAIN_GARDEN',
      areaM2: 10,
      installedAt: '2026-10-19T00:00:00Z',
      seasonEndsAt: '2026-10-25T15:00:00Z',
      scoreM3,
      evaluatedMinutes: n ? 3 : 0,
      evaluatedThrough: n ? '2026-10-19T00:03:00Z' : null,
    })),
    nextAfterId: null,
  });
  const html = renderToStaticMarkup(
    <SiteScoreRows value={value} viewerId={value.installations[0].ownerId} />
  );
  expect(html).toContain('내 시설');
  expect(html).toContain('회원1');
  expect(html).toContain('회원2');
  expect(html).toContain('미계산');
  expect(html).toContain('>0 m³<');
  expect(html).toContain('-0.125 m³');
  expect(html).toContain('계산 반영');
});
