import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import fixture from '../view/fixtures/public-node-flooding-job.json';
import durationFixture from '../view/fixtures/public-node-flood-duration-v1.json';
import { nodeFloodingDto } from '../dto/nodeFloodingDto';
import { watershedLayoutDto } from '../dto/watershedLayoutDto';
import { watershedJobDto } from '../dto/watershedDto';
import { compareNodeFlooding, floodNodeColor } from './nodeFlooding';
import { WatershedResult } from '../view/WatershedResult';
import { WatershedFloodMap } from '../view/WatershedFloodMap';

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
  expect(html).toContain('월류 발생 시간 · 이 기록에는 시간 자료가 없습니다.');
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

it('실제 서버 결과의 월류 시간 감소·악화 보존과 지표 저류 시간 구분', () => {
  const baseline = nodeFloodingDto.parse(durationFixture.baseline);
  const strategy = nodeFloodingDto.parse(durationFixture.strategy);
  const rows = compareNodeFlooding(baseline, strategy);
  expect(rows.find((n) => n.id === 'J22')!.reductionSeconds).toBeCloseTo(0.744, 8);
  expect(rows.find((n) => n.id === 'J23')!.reductionSeconds).toBeCloseTo(-2.17, 8);
  expect(rows.find((n) => n.id === 'Out1')!.baselineSeconds).toBe(0);
  const html = renderToStaticMarkup(
    <WatershedFloodMap
      layout={watershedLayoutDto.parse(durationFixture.layout)}
      baseline={baseline}
      strategy={strategy}
    />
  );
  expect(html).toContain('월류 발생 시간 · 설치 전');
  expect(html).toContain('0.744초 감소');
  expect(html).toContain('지표에 물이 고인 시간은 제외');
  expect(html).not.toContain('이 기록에는 시간 자료가 없습니다');
});

it('월류 시간의 부분 누락·잘못된 방법·기간 초과·비유한 수·방류구 양수 시간 거부', () => {
  for (const change of [
    'partial',
    'method',
    'missing-method',
    'negative',
    'over',
    'nan',
    'outfall',
  ]) {
    const raw = structuredClone(durationFixture.strategy);
    if (change === 'partial') Reflect.deleteProperty(raw.nodes[0], 'floodingSeconds');
    if (change === 'method') raw.durationMethod = 'EPA_TIME_FLOODED';
    if (change === 'missing-method') Reflect.deleteProperty(raw, 'durationMethod');
    if (change === 'negative') raw.nodes[0].floodingSeconds = -1;
    if (change === 'over') raw.nodes[0].floodingSeconds = raw.endSeconds + 1;
    if (change === 'nan') raw.nodes[0].floodingSeconds = Number.NaN;
    if (change === 'outfall') raw.nodes.find((n) => n.kind === 'OUTFALL')!.floodingSeconds = 1;
    expect(nodeFloodingDto.safeParse(raw).success, change).toBe(false);
  }
});
