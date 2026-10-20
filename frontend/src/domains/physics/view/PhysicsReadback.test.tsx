import { expect, it } from 'vitest';
import physics from './fixtures/rawMetrics-physics-http-v1.json';
import weekly from './fixtures/rawMetrics-weekly-http-v1.json';
import { physicsDto } from '../dto/physicsDto';
import { weeklyDto } from '../../weekly/dto/weeklyDto';

it('실제 공개 HTTP 주간 응답의 저장 설계 근거와 현재 비교 계약 결속', () => {
  expect(physics.classification).toBe('ACTUAL_PUBLIC_HTTP_RESPONSE_WITH_SYNTHETIC_TEST_WEATHER');
  const value = physicsDto.parse(physics.value);
  expect(value.result!.designContract!.sha256).toMatch(/^[a-f0-9]{64}$/);
  expect(value.result!.runoffComparison!.schemaVersion).toBe(2);
  expect(value.result!.runoffComparison!.metricComparison!.window).toEqual({
    kind: 'UTC',
    start: value.result!.designContract!.evaluation.start,
    end: value.result!.designContract!.evaluation.end,
  });
  const changed = structuredClone(value);
  changed.result!.designContract = null;
  expect(physicsDto.safeParse(changed).success).toBe(false);
  changed.result!.runoffComparison!.schemaVersion = 1;
  expect(physicsDto.safeParse(changed).success).toBe(true);
});

it('실제 주간 API의 미평가 null·순위 없음과 0 치환 거부', () => {
  const value = weeklyDto.parse(weekly.value);
  const missing = value.current.districts.filter((d) => d.evaluatedSeconds === 0);
  expect(missing.length).toBeGreaterThan(0);
  expect(missing.every((d) => d.scoreM3 === null && d.rank === null)).toBe(true);
  const changed = structuredClone(value);
  changed.current.districts.find((d) => d.evaluatedSeconds === 0)!.scoreM3 = 0;
  expect(weeklyDto.safeParse(changed).success).toBe(false);
});
