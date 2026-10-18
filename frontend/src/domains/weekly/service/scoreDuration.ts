type Evaluated = { evaluatedSeconds?: number; evaluatedMinutes: number };
type Expected = { expectedSeconds?: number; expectedMinutes: number };
export const evaluatedSeconds = (value: Evaluated) =>
  value.evaluatedSeconds ?? value.evaluatedMinutes * 60;
export const expectedSeconds = (value: Expected) =>
  value.expectedSeconds ?? value.expectedMinutes * 60;
export function scoreDuration(value: Evaluated) {
  const seconds = evaluatedSeconds(value);
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return [
    minutes ? `${minutes.toLocaleString('ko-KR')}분` : '',
    remainder || !minutes ? `${remainder}초` : '',
  ]
    .filter(Boolean)
    .join(' ');
}
