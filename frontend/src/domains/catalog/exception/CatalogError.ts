export class CatalogError extends Error {
  constructor(public readonly code: 'NETWORK' | 'INVALID_DATA') {
    super(
      code === 'NETWORK' ? '공개자료를 불러오지 못했습니다.' : '자료 형식을 확인하지 못했습니다.'
    );
  }
}
