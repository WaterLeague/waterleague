import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import fixture from '../view/fixtures/public-node-flooding-job.json';
import { watershedJobDto } from '../dto/watershedDto';
import { compareNodeFlooding, floodNodeColor } from './nodeFlooding';
import { WatershedResult } from '../view/WatershedResult';

it('실제 혼합 설계의 지점별 개선·악화와 위치 없는 저류조 보존', () => {
  const job = watershedJobDto.parse(fixture);
  const [base, strategy] = job.result!.cases;
  const rows = compareNodeFlooding(base.nodeFlooding!, strategy.nodeFlooding!);
  expect(rows).toHaveLength(28);
  expect(rows.find((n) => n.id === 'J3')!.reductionM3).toBeCloseTo(-1318.2270847506747, 8);
  expect(rows.find((n) => n.id === 'J20')!.reductionM3).toBeCloseTo(1452.1756389495786, 8);
  expect(rows.some((n) => n.id === 'WLST_Tank')).toBe(false);
  const html = renderToStaticMarkup(<WatershedResult job={job} />);
  expect(html).toContain('어디에서 물이 넘쳤나');
  expect(html).toContain('좌표 없는 추가 설계 1개');
  expect(html).toContain('원본 관망 지점별 누적 월류');
  expect(html).toContain('지표 침수 깊이·침수 구역을 뜻하지 않습니다');
  expect(html).toContain('J3 · 1,318.2 m³ 증가');
});

it('월류 합계·중복·지도 결속·비교 창·절점 누락 거부', () => {
  for (const kind of [
    'sum',
    'duplicate',
    'hash',
    'time',
    'missing',
    'kind',
    'unmapped',
    'no-report',
    'no-layout',
  ]) {
    const raw = structuredClone(fixture);
    const report = raw.result.cases[1].nodeFlooding;
    if (kind === 'sum') report.nodes[0].floodingM3 += 20;
    if (kind === 'duplicate') report.nodes[1].id = report.nodes[0].id;
    if (kind === 'hash') report.layoutSha256 = '0'.repeat(64);
    if (kind === 'time') report.endSeconds += 1;
    if (kind === 'missing')
      report.nodes.splice(
        report.nodes.findIndex((n) => n.id === 'Out1'),
        1
      );
    if (kind === 'kind') report.nodes[0].kind = 'OUTFALL';
    if (kind === 'unmapped') report.nodes[0].mapped = false;
    if (kind === 'no-report') Reflect.deleteProperty(raw.result.cases[1], 'nodeFlooding');
    if (kind === 'no-layout') Reflect.deleteProperty(raw.result, 'networkLayout');
    expect(watershedJobDto.safeParse(raw).success, kind).toBe(false);
  }
});

it('실패 결과에 개선도 비노출 및 과거 기록 호환', () => {
  const failed = structuredClone(fixture);
  failed.result.numericalStatus = 'FAILED';
  Reflect.set(failed.result, 'signedReductionM3', null);
  Reflect.set(failed.result, 'signedPeakReductionM3s', null);
  const html = renderToStaticMarkup(<WatershedResult job={watershedJobDto.parse(failed)} />);
  expect(html).not.toContain('어디에서 물이 넘쳤나');
  const old = structuredClone(fixture);
  Reflect.deleteProperty(old.result, 'networkLayout');
  old.result.cases.forEach((c) => Reflect.deleteProperty(c, 'nodeFlooding'));
  expect(watershedJobDto.safeParse(old).success).toBe(true);
});

it('기준·설계 동일 색상 척도와 변화 부호 유지', () => {
  expect(floodNodeColor('baseline', 4, 10)).toBe(floodNodeColor('strategy', 4, 10));
  expect(floodNodeColor('change', -4, 10)).not.toBe(floodNodeColor('change', 4, 10));
  expect(floodNodeColor('change', 0, 0)).toBe('#cad3cf');
});
