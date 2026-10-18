import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { playbackCatalogDto, playbackFrameDto } from '../dto/playbackDto';
import { requirePlaybackBinding, recordedFlowPoints } from './playback';
import { WatershedPlaybackView } from '../view/WatershedPlayback';
import sample from '../view/fixtures/public-pump-job.json';
import { watershedJobDto } from '../dto/watershedDto';
const jobId = '00000000-0000-4000-8000-000000000001';
const sources = ['baseline', 'strategy'].map((id) => ({
  id,
  framesSha256: 'a'.repeat(64),
  resultSha256: 'b'.repeat(64),
  numericalStatus: 'PASSED',
}));
const catalog = playbackCatalogDto.parse({
  jobId,
  inputHash: 'c'.repeat(64),
  method: 'PREVIOUS_RECORDED_STATE_NO_INTERPOLATION',
  depthScaleM: 3,
  timesSeconds: [0, 5, 6, 10],
  sources,
});
const frame = playbackFrameDto.parse({
  jobId,
  inputHash: catalog.inputHash,
  requestedTimeSeconds: 5,
  cases: sources.map((s, i) => ({
    ...s,
    ageSeconds: i ? 5 : 0,
    state: {
      timeSeconds: i ? 0 : 5,
      nodes: [{ id: 'J1', type: 0, headM: 10, depthM: 1, storageM3: 3, overflowM3s: 0 }],
      links: [{ id: 'C1', flowM3s: -2, depthM: 0.2, setting: 1 }],
    },
  })),
});
describe('원 관망 기록 재생', () => {
  it('원본 결속과 서로 다른 실제 기록 시각 유지', () => {
    expect(requirePlaybackBinding(catalog, frame, 5)).toBe(frame);
    expect(() => requirePlaybackBinding(catalog, frame, 6)).toThrow();
    expect(() =>
      requirePlaybackBinding(catalog, { ...frame, inputHash: 'd'.repeat(64) }, 5)
    ).toThrow();
    expect(
      playbackFrameDto.safeParse({
        ...frame,
        cases: frame.cases.map((c) => ({ ...c, ageSeconds: 0 })),
      }).success
    ).toBe(false);
    expect(playbackCatalogDto.safeParse({ ...catalog, timesSeconds: [0, 5, 4] }).success).toBe(
      false
    );
  });
  it('부호에 따른 역류 방향과 원본 선형 불변', () => {
    const points = [
      [0, 0],
      [1, 2],
      [3, 4],
    ];
    expect(recordedFlowPoints(points, -2)).toEqual([
      [3, 4],
      [1, 2],
      [0, 0],
    ]);
    expect(recordedFlowPoints(points, 0)).toBe(points);
    expect(recordedFlowPoints(points, 2)).toBe(points);
  });
  it('같은 요청 시각의 두 기록과 깊이 구분 표시', () => {
    const job = watershedJobDto.parse(sample);
    const html = renderToStaticMarkup(
      <WatershedPlaybackView
        layout={job.result!.networkLayout!.layout}
        catalog={catalog}
        frame={frame}
        index={1}
        playing={false}
        onIndex={() => {}}
        onPlaying={() => {}}
      />
    );
    expect(html).toContain('관망 재생 시각');
    expect(html).toContain('설치 전 기록:');
    expect(html).toContain('지표 침수 깊이가 아닙니다');
    expect(html).toContain('원 연구 입력의 상대 시각');
    expect(html).toContain('절점 내부 수심');
  });
});
