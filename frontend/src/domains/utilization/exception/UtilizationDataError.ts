export class UtilizationDataError extends Error {
  constructor() {
    super('활용 요청과 동의 이력의 연결을 확인하지 못했습니다. 새로고침해 주세요.');
  }
}
