import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { GameplayScoreboard } from './GameplayScoreboard';
import { installationScore } from '../../installation/service/installationScore';

it('점수 없음·계산된 0·악화 점수를 지도 점수판에서 구분', () => {
  for (const [score, text] of [
    [null, '점수 없음'],
    [0, '0'],
    [-0.125, '-0.125'],
    [-1e-9, '-1.00e-9'],
    [1e-9, '1.00e-9'],
  ] as const) {
    const html = renderToStaticMarkup(
      <GameplayScoreboard
        historical={false}
        authenticated
        district={{
          districtId: '11200',
          districtName: '성동구',
          rank: score === null ? null : 1,
          scoreM3: score,
          scoreM3Exact: score === null ? null : score.toFixed(9),
          evaluatedSeconds: score === null ? 0 : 60,
          evaluatedMinutes: score === null ? 0 : 1,
          expectedSeconds: 60,
          expectedMinutes: 1,
        }}
        weekly={null}
        count={1}
        score={score}
      />
    );
    if (score === null) {
      expect(html.match(/점수 없음/g)).toHaveLength(2);
      expect(html).not.toContain('>0<');
      expect(html).not.toContain('> m³<');
    } else {
      expect(html).not.toContain('점수 없음');
      expect(html.split(`>${text}<`).length - 1).toBe(2);
    }
  }
});

it('설치 목록의 미반영 점수와 실제 0 및 음수 보존', () => {
  expect(installationScore({ scoreM3: null })).toBe('점수 없음');
  expect(installationScore({ scoreM3: 0 })).toBe('0 m³');
  expect(installationScore({ scoreM3: -0.125 })).toBe('-0.125 m³');
  expect(installationScore({ scoreM3: -1e-9 })).toBe('-1.00e-9 m³');
});
