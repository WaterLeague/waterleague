export class ReferenceDataError extends Error {
  constructor() {
    super('CPU 기준안의 계산 조건을 확인하지 못했습니다.');
  }
}
