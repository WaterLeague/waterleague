import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import ordinary from './fixtures/public-cistern-inlet-job-v1.json';
import flooded from './fixtures/public-cistern-inlet-flood-job-v1.json';
import { watershedJobDto } from '../dto/watershedDto';
import { WatershedResult } from './WatershedResult';

it('실제 소유자 API의 연결관 입력과 입구 월류·효과 보류 표시', () => {
  for (const fixture of [ordinary, flooded]) {
    expect(fixture.evidence).toBe('ACTUAL_API_WORKER_DTO_PROJECTION_NOT_AUTHENTICATED_BROWSER');
    const job = watershedJobDto.parse(fixture.job);
    const pipe = job.design.cistern!.inletPipe!;
    const ledger = job.result!.cases[1].networkCistern!.wholeRunLedger.inletPipe!;
    const html = renderToStaticMarkup(<WatershedResult job={job} />);
    expect(pipe.lengthM).toBe(10);
    expect(html).toContain('집수 연결관 · 길이 10');
    expect(html).toContain('집수 연결관 입구');
    if (fixture === flooded) {
      expect(ledger.floodingM3).toBeGreaterThan(0);
      expect(job.result!.signedReductionM3).toBeNull();
      expect(job.result!.numericalStatus).toBe('FAILED');
      expect(html).toContain('효과 비교 보류');
    } else {
      expect(ledger.floodingM3).toBe(0);
      expect(job.result!.numericalStatus).toBe('PASSED');
    }
  }
});

it('연결관·입구 원장 누락과 월류 은폐·좌표 위조 결과 거부', () => {
  for (const fixture of [ordinary, flooded]) {
    const original = watershedJobDto.parse(fixture.job);
    const mutations: Array<(v: typeof original) => void> = [
      (v) => {
        delete v.design.cistern!.inletPipe;
      },
      (v) => {
        delete v.result!.cases[1].networkCistern!.wholeRunLedger.inletPipe;
      },
      (v) => {
        v.result!.cases[1].networkCistern!.wholeRunLedger.inletPipe!.nodeId = 'Unbound';
      },
      (v) => {
        v.result!.cases[1].networkCistern!.wholeRunLedger.inletPipe!.floodingM3 += 1;
      },
      (v) => {
        v.result!.cases[1].nodeFlooding!.nodes.find((n) => n.id === 'WLCT_Cistern1_U')!.mapped =
          true;
      },
    ];
    for (const mutate of mutations) {
      const changed = structuredClone(original);
      mutate(changed);
      expect(watershedJobDto.safeParse(changed).success).toBe(false);
    }
  }
  const hidden = watershedJobDto.parse(flooded.job);
  hidden.result!.cases[1].networkCistern!.wholeRunLedger.inletPipe!.numericalStatus = 'PASSED';
  expect(watershedJobDto.safeParse(hidden).success).toBe(false);
});
