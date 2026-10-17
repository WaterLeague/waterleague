export class SearchDataError extends Error {
  constructor() {
    super('후보 탐색 자료의 연결 또는 수치가 일치하지 않습니다. 다시 조회해 주세요.');
    this.name = 'SearchDataError';
  }
}
