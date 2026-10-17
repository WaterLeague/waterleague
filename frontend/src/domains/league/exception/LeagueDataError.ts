export class LeagueDataError extends Error {
  constructor() {
    super('리그의 고정 규칙을 확인할 수 없습니다. 다시 불러와 주세요.');
  }
}
