import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import fixture from './fixtures/cistern-demand-v1.json';
import httpFixture from './fixtures/cistern-demand-http-v1.json';
import { physicsDto } from '../../physics/dto/physicsDto';
import { cisternGameDto } from '../dto/cisternGameDto';
import { CisternGameEvidence } from './CisternGameEvidence';

describe('관측 강우를 사용한 이용조 수요 비교', () => {
  it('주간과 전체 사건의 실제 워커 결과를 표시하고 가정과 실사용을 구별', () => {
    for (const raw of [fixture.weekly, fixture.fullEvent, fixture.experiment]) {
      const value = cisternGameDto.parse(raw);
      const html = renderToStaticMarkup(<CisternGameEvidence value={value} />);
      expect(html).toContain('하루 201L 수요 가정');
      expect(html).toContain('잠재 공급');
      expect(html).toContain('부족');
      expect(html).toContain('실제 사용량은 미확인');
      expect(html).toContain('선행·설치 이전 공급 제외');
      expect(html).toContain('순위에 가산하지 않습니다');
      expect(html).toContain('화성시 가구 수요 가정');
      expect(html).toContain('https://journal.cricit.kr/jkswe/XmlViewer/f253405');
    }
  });

  it('실제 주간 HTTP 응답을 수용하고 다른 평가 창의 공급 자료는 거부', () => {
    expect(physicsDto.safeParse(httpFixture).success).toBe(true);
    const changed = structuredClone(httpFixture);
    changed.result.simulatedThrough = '2022-08-08T23:59:00Z';
    expect(physicsDto.safeParse(changed).success).toBe(false);
  });

  it('과거 자연배수 결과에 수요 계산이나 0 공급을 덧붙이지 않음', () => {
    const { demandScenario: _unused, ...old } = fixture.weekly;
    const value = cisternGameDto.parse(old);
    const html = renderToStaticMarkup(<CisternGameEvidence value={value} />);
    expect(html).toContain('재이용량 미산정');
    expect(html).not.toContain('잠재 공급');
    expect(html).not.toContain('수요 비교의 계산 근거');
  });

  it('초과 공급·일수요·기간·저류·출처 변조를 거부', () => {
    const invalid = [
      { suppliedM3: 200 },
      { demandM3: 200 },
      { demandRateM3Day: 200 },
      { evaluationSeconds: 1 },
      { finalStorageM3: 200 },
      { unmetDemandM3: 200 },
      { supplyFraction: 2 },
      { rankingEligible: true },
      { observedReuseM3: 1 },
      { source: { ...fixture.weekly.demandScenario.source, url: 'https://example.com' } },
    ];
    for (const update of invalid) {
      const changed = {
        ...fixture.weekly,
        demandScenario: { ...fixture.weekly.demandScenario, ...update },
      };
      expect(cisternGameDto.safeParse(changed).success).toBe(false);
    }
    expect(cisternGameDto.safeParse({ ...fixture.weekly, capacityM3: 200 }).success).toBe(false);
  });

  it('검증되지 않은 재해 응답은 공급 수치를 표시하지 않음', () => {
    const value = cisternGameDto.parse(fixture.weekly);
    value.demandScenario!.suppliedM3 = 200;
    const html = renderToStaticMarkup(<CisternGameEvidence value={value} />);
    expect(html).toContain('수요 비교의 계산 근거를 확인할 수 없습니다');
    expect(html).not.toContain('잠재 공급');
  });
});
