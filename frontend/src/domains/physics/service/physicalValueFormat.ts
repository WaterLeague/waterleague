// 작은 양·음의 효과를 0으로 바꾸지 않고 표시 자릿수만 줄인다.
export const physicalAmount = (v: number) =>
  v !== 0 && Math.abs(v) < 0.00001
    ? v.toExponential(2)
    : v.toLocaleString('ko-KR', { maximumSignificantDigits: 5 });
