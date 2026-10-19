export function partBounds(positions: Float32Array, ends: number[]) {
  const bounds = new Float32Array(ends.length * 6);
  let start = 0;
  ends.forEach((end, i) => {
    const minimum = [Infinity, Infinity, Infinity],
      maximum = [-Infinity, -Infinity, -Infinity];
    for (let v = start * 9; v < end * 9; v += 3)
      for (let k = 0; k < 3; k++) {
        minimum[k] = Math.min(minimum[k], positions[v + k]);
        maximum[k] = Math.max(maximum[k], positions[v + k]);
      }
    bounds.set([...minimum, ...maximum], i * 6);
    start = end;
  });
  return bounds;
}
