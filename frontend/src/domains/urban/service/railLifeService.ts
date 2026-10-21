import type { StreetPath } from './streetLifeService';
import { pathPosition, stableSeed } from './streetLifeService';
export const TRAIN_CAR_LENGTH_M = 18;
export function trainCarriages(path: StreetPath, seconds: number) {
  const count = Math.min(4, Math.max(1, Math.floor(path.length / 50)));
  const seed = stableSeed(path.road.id);
  const direction = seed > 0.5 ? 1 : -1;
  const cycle = path.length + count * 20;
  const speed = path.road.nativeRailKind === 'subway' ? 10 : 12;
  const head = (((seconds * speed + seed * cycle) % cycle) + cycle) % cycle;
  const result = [];
  for (let car = 0; car < count; car++) {
    const along = head - car * 20;
    if (along < 9 || along > path.length - 9) continue;
    const distance = direction > 0 ? along : path.length - along;
    const center = pathPosition(path, distance, 0, direction);
    const front = pathPosition(path, distance + 8 * direction, 0, direction);
    const back = pathPosition(path, distance - 8 * direction, 0, direction);
    result.push({ center, front, back, car, direction, distance });
  }
  return result;
}
