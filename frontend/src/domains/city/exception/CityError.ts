export class CityError extends Error {
  constructor(kind: 'NETWORK' | 'INVALID_DATA') {
    super(
      kind === 'NETWORK'
        ? '서울 지도 자료를 불러오지 못했습니다. 다시 시도해 주세요.'
        : '서울 지도 자료의 무결성 검사를 통과하지 못했습니다.'
    );
    this.name = 'CityError';
  }
}
