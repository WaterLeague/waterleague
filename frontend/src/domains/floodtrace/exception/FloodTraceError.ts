export class FloodTraceError extends Error {
  constructor() {
    super('침수흔적 자료를 불러오지 못했습니다. 다시 시도해 주세요.');
  }
}
