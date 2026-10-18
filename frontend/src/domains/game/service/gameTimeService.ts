export const rainDate = (value: string) =>
  new Date(value).toLocaleDateString('ko-KR', { timeZone: 'Asia/Seoul' });
