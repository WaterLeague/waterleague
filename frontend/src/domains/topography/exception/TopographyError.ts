export class TopographyError extends Error {
  constructor() {
    super('지형지물 자료를 불러오지 못했습니다. 다시 시도해 주세요.');
    this.name = 'TopographyError';
  }
}
