import { expect, test } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { HomePage } from './HomePage';
import { GamePage } from '../../game/view/GamePage';
import { facilities } from '../../game/service/gameService';
import { homeFacilities, homeModes } from '../service/homeContent';
import { dataSources } from '../../catalog/service/dataSourceService';
import { GameStartDialog } from './GameStartDialog';
import { infrastructureNames } from '../../infrastructure/service/infrastructureService';

test('홈에서 실제 설치 시설 7종과 두 게임 모드·각 기능으로 연결', () => {
  const html = renderToStaticMarkup(<HomePage />);
  expect(homeFacilities.map((item) => item.type).sort()).toEqual(Object.keys(facilities).sort());
  for (const item of homeFacilities) expect(html).toContain(facilities[item.type].name);
  for (const mode of homeModes) {
    expect(html).toContain(`href="${mode.href}"`);
    expect(html).toContain(`${mode.title} 3D 미리보기`);
  }
  for (const href of ['/rankings', '/competitions', '/#home-data'])
    expect(html).toContain(`href="${href}"`);
  expect(html).toContain('/brand/otter.png');
  expect(html).toContain('/brand/kingfisher.png');
  expect(html).toContain('수달 여울이');
  expect(html).toContain('물총새 가람이');
  expect(html).toContain('aria-pressed="true"');
  expect(html).toContain('빗물정원 왼쪽으로 회전');
  expect(html).toContain('로그인 후 사건 전체 설계 제출');
  expect(html).toContain('과거 침수 기록 3D 미리보기');
  expect(html).toContain('빗물펌프장 3D 미리보기');
  for (const name of Object.values(infrastructureNames)) expect(html).toContain(name);
  expect(html).not.toContain('지도에서 표시되는 허용 후보에 설치해요');
  expect(html).not.toContain('지도에서 배치해 보기');
});

test('게임 시작은 선택 창을 열며 각 모드의 주소와 이용 조건을 제공', () => {
  const home = renderToStaticMarkup(<HomePage />);
  expect(home).toMatch(/<button[^>]*aria-haspopup="dialog"[^>]*>게임 시작하기/);
  const dialog = renderToStaticMarkup(<GameStartDialog onClose={() => {}} />);
  expect(dialog).toContain('aria-labelledby="game-start-title"');
  for (const mode of homeModes) {
    expect(dialog).toContain(`href="${mode.href}"`);
    expect(dialog).toContain(mode.title);
  }
  expect(dialog).toContain('로그인 후 우리 구에 설치');
  expect(dialog).toContain('로그인 없이 체험');
  expect(dialog).toContain('게임 모드 선택 닫기');
});

test('홈에 점수식·예시·모드별 기간과 순위 한계를 소개', () => {
  const html = renderToStaticMarkup(<HomePage />);
  expect(html).toContain('id="home-score"');
  expect(html.indexOf('id="home-modes"')).toBeLessThan(html.indexOf('id="home-facilities-title"'));
  expect(html.indexOf('id="home-facilities-title"')).toBeLessThan(html.indexOf('id="home-map"'));
  expect(html.indexOf('id="home-map"')).toBeLessThan(html.indexOf('id="home-score"'));
  for (const text of [
    '표면 유출 + 시설 배수 + 종료 저류량 − 시작 저류량',
    '설명용 예시',
    '공동 순위',
    '개인 최고 기록',
    '음수도 그대로 합산',
    '접수 기간',
  ])
    expect(html).toContain(text);
});

test('기본 주소는 소개 홈이며 새 텍스트 로고가 홈으로 연결', () => {
  const html = renderToStaticMarkup(<GamePage />);
  expect(html).toContain('id="home-title"');
  expect(html).toContain('href="/" aria-label="WATER LEAGUE 홈"');
  expect(html).toContain('/brand/wordmark.png');
  expect(html).toContain('href="/" aria-current="page"');
  expect(html).not.toContain('city-stage');
  expect(html).not.toContain('시민의 설계, 도시의 변화');
  expect(html).not.toContain('href="/data"');
  expect(html.match(/<nav.*?<\/nav>/)?.[0]).not.toContain('데이터');
});

test('데이터의 모든 출처와 비용·계산 설명을 홈 마지막 콘텐츠로 유지', () => {
  const html = renderToStaticMarkup(<HomePage />);
  const section = html.slice(html.indexOf('id="home-data"'), html.indexOf('<footer'));
  expect(html.indexOf('id="home-data"')).toBeGreaterThan(html.indexOf('class="home-start"'));
  for (const source of dataSources) {
    expect(section).toContain(source.title);
    for (const dataset of source.datasets) {
      expect(section).toContain(renderToStaticMarkup(<span>{dataset.name}</span>));
      expect(section).toContain(dataset.href.replaceAll('&', '&amp;'));
    }
  }
  for (const facility of Object.values(facilities)) expect(section).toContain(facility.name);
  expect(section).toContain('예산·설치비');
  expect(section).toContain('data-maintenance-reference');
  expect(section).toContain('data-assessment-rules');
  expect(section).toContain('data-calculation');
  expect(html.match(/<h1\b/g)).toHaveLength(1);
});
