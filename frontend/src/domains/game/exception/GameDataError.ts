export class GameDataError extends Error {
  constructor() {
    super('실험 자료의 단위·시간·형식을 확인할 수 없습니다. 다시 불러와 주세요.');
    this.name = 'GameDataError';
  }
}
