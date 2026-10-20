import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import ordinary from './fixtures/public-cistern-outlets-job-v1.json';
import flooded from './fixtures/public-cistern-outletflood-job-v1.json';
import { watershedJobDto, type WatershedJob } from '../dto/watershedDto';
import { WatershedResult } from './WatershedResult';

it('인증 HTTP의 배수·월류 접속관과 넘침·비교 보류 표시', () => {
  for (const fixture of [ordinary, flooded]) {
    expect(fixture.evidence).toBe('ACTUAL_AUTHENTICATED_HTTP_WORKER_PROJECTION_NOT_BROWSER');
    const job = watershedJobDto.parse(fixture.job);
    const pipes = job.result!.cases[1].networkCistern!.wholeRunLedger.outletPipes!;
    const html = renderToStaticMarkup(<WatershedResult job={job} />);
    expect(html).toContain('일반 배수 연결관 · 길이 10');
    expect(html).toContain('비상 배수 연결관 접속부');
    expect(pipes.drain!.receiverNodeId).toBe('J22');
    if (fixture === flooded) {
      expect(pipes.drain!.floodingM3).toBeGreaterThan(0);
      expect(job.result!.signedReductionM3).toBeNull();
      expect(job.result!.numericalStatus).toBe('FAILED');
      expect(html).toContain('효과 비교 보류');
    } else {
      expect(pipes.drain!.floodingM3).toBe(0);
      expect(job.result!.numericalStatus).toBe('PASSED');
    }
  }
});

it('출구 연결관 누락·다른 하류 연결·월류 은폐·가짜 위치 거부', () => {
  for (const fixture of [ordinary, flooded]) {
    const original = watershedJobDto.parse(fixture.job);
    const mutations: Array<(v: WatershedJob) => void> = [
      (v) => {
        delete v.design.cistern!.drainPipe;
      },
      (v) => {
        delete v.result!.cases[1].networkCistern!.wholeRunLedger.outletPipes;
      },
      (v) => {
        v.result!.cases[1].networkCistern!.wholeRunLedger.outletPipes!.drain!.nodeId = 'Unbound';
      },
      (v) => {
        v.result!.cases[1].networkCistern!.wholeRunLedger.outletPipes!.drain!.receiverNodeId = 'J1';
      },
      (v) => {
        v.result!.cases[1].networkCistern!.wholeRunLedger.outletPipes!.drain!.floodingM3 += 1;
      },
      (v) => {
        v.result!.cases[1].nodeFlooding!.nodes.find((n) => n.id === 'WLCT_Cistern1_DJ')!.mapped =
          true;
      },
      (v) => {
        v.design.cistern!.drain = { mode: 'CLOSED_NO_WITHDRAWAL' };
      },
    ];
    for (const mutate of mutations) {
      const changed = structuredClone(original);
      mutate(changed);
      expect(watershedJobDto.safeParse(changed).success).toBe(false);
    }
  }
  const hidden = watershedJobDto.parse(flooded.job);
  hidden.result!.cases[1].networkCistern!.wholeRunLedger.outletPipes!.drain!.numericalStatus =
    'PASSED';
  expect(watershedJobDto.safeParse(hidden).success).toBe(false);
});
