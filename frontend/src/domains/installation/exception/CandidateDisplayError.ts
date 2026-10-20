export class CandidateDisplayError extends Error {
  constructor() {
    super('설치 가능 구역을 불러오지 못했습니다. 다시 시도해 주세요.');
    this.name = 'CandidateDisplayError';
  }
}
