export class ComparisonDataError extends Error {
  constructor() {
    super('강우 비교의 저장 버전과 결과 연결을 확인하지 못했습니다.');
  }
}
