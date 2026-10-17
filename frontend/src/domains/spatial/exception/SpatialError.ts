export class SpatialError extends Error {
  constructor() {
    super('공간자료의 좌표·응답 품질 검사를 통과하지 못했습니다.');
    this.name = 'SpatialError';
  }
}
