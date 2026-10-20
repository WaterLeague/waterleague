const ordinary = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 3 });
export const scoreFormat = {
  // 작은 기여·악화를 표시 반올림으로 0으로 숨기지 않는다.
  format: (value: number) =>
    value !== 0 && Math.abs(value) < 0.001 ? value.toExponential(2) : ordinary.format(value),
};
