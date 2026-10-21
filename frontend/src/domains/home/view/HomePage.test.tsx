import { expect, test } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { HomePage } from './HomePage';
import { GamePage } from '../../game/view/GamePage';
import { facilities } from '../../game/service/gameService';
import { homeFacilities, homeModes } from '../service/homeContent';

test('홈에서 실제 설치 시설 7종과 두 게임 모드·각 기능으로 연결', () => {
  const html = renderToStaticMarkup(<HomePage />);
  expect(homeFacilities.map((item) => item.type).sort()).toEqual(Object.keys(facilities).sort());
  for (const item of homeFacilities) expect(html).toContain(facilities[item.type].name);
  for (const mode of homeModes) {
    expect(html).toContain(`href="${mode.href}"`);
    expect(html).toContain(`${mode.title} 3D 미리보기`);
  }
  for (const href of ['/rankings', '/competitions', '/data'])
    expect(html).toContain(`href="${href}"`);
  expect(html).toContain('/brand/otter.png');
  expect(html).toContain('/brand/kingfisher.png');
  expect(html).toContain('aria-pressed="true"');
  expect(html).toContain('빗물정원 왼쪽으로 회전');
  expect(html).toContain('로그인 후 사건 전체 설계 제출');
});

test('기본 주소는 소개 홈이며 새 텍스트 로고가 홈으로 연결', () => {
  const html = renderToStaticMarkup(<GamePage />);
  expect(html).toContain('id="home-title"');
  expect(html).toContain('href="/" aria-label="WATER LEAGUE 홈"');
  expect(html).toContain('/brand/wordmark.png');
  expect(html).toContain('href="/" aria-current="page"');
  expect(html).not.toContain('city-stage');
  expect(html).not.toContain('시민의 설계, 도시의 변화');
});
