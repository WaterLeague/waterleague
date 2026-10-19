export function mapNearPlane(distance: number, groundClearance: number) {
  // 노면·수면의 깊이 차이를 보존하되 지면 가까이에서는 앞쪽 잘림을 제한한다.
  return Math.max(1, Math.min(distance / 10, groundClearance / 2));
}
