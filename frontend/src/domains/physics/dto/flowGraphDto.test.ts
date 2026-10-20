import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';
import native from '../view/fixtures/nativeFlowGraph.json';
import { designContractDto } from './designContractDto';
import { RunoffComparison } from '../view/RunoffComparison';

it('실제 원형 워커의 면적 배분·출처·평가 경계를 기존 비교 결과에 결속', () => {
  expect(designContractDto.safeParse(native.contract).success).toBe(true);
  const html = renderToStaticMarkup(
    createElement(RunoffComparison, { value: native.comparison, contract: native.contract })
  );
  expect(html).toContain('배수 관망·지표 침수 격자 미연결');
  expect(html).not.toContain('범위 근거를 확인하지 못했습니다');
});

it('중복 배분·면적 초과·출처 불일치·누락 노드·다른 평가 지점을 정상 연결로 표시하지 않음', () => {
  const mutations = [
    (g: typeof native.contract.flowGraph) =>
      g.areaBudgets[0].allocations.push(g.areaBudgets[0].allocations[0]),
    (g: typeof native.contract.flowGraph) => {
      g.areaBudgets[0].allocations[0].areaM2 = '999999999';
    },
    (g: typeof native.contract.flowGraph) => {
      const rows = g.areaBudgets[0].allocations;
      [rows[0].areaM2, rows[1].areaM2] = [rows[1].areaM2, rows[0].areaM2];
    },
    (g: typeof native.contract.flowGraph) => {
      g.sourceHashes['model.json'] = '0'.repeat(64);
    },
    (g: typeof native.contract.flowGraph) => {
      g.nodes[0].source = 'toString';
    },
    (g: typeof native.contract.flowGraph) => {
      g.edges[0].to = 'MISSING';
    },
    (g: typeof native.contract.flowGraph) => {
      g.evaluationPoints[0].nodeId = g.nodes[0].id;
    },
    (g: typeof native.contract.flowGraph) => {
      g.areaBudgets[0].allocations[0].areaM2 = '1e999999';
    },
    (g: typeof native.contract.flowGraph) => {
      g.evaluationPoints[0].start = '2022-08-08T09:09:00+00:00';
    },
  ];
  for (const mutate of mutations) {
    const contract = structuredClone(native.contract);
    mutate(contract.flowGraph);
    expect(designContractDto.safeParse(contract).success).toBe(false);
    const html = renderToStaticMarkup(
      createElement(RunoffComparison, { value: native.comparison, contract })
    );
    expect(html).toContain('설계·평가 범위 근거를 확인하지 못했습니다');
    expect(html).not.toContain('배수 관망·지표 침수 격자 미연결');
  }
});
