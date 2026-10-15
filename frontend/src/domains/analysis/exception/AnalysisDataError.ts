export class AnalysisDataError extends Error {
  constructor() {
    super('분석의 원본 연결과 집계 범위를 확인하지 못했습니다. 다시 조회해 주세요.');
  }
}
