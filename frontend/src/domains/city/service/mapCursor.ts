import type { ThreeEvent } from '@react-three/fiber';
export type MapCursor = 'install' | 'inspect';
const paths = {
  install: '<path d="m12 3 10 5-10 5L2 8l10-5Zm-10 9 10 5 10-5M2 16l10 5 10-5"/>',
  inspect: '<circle cx="10" cy="10" r="7"/><path d="m15 15 7 7M10 7v6M7 10h6"/>',
};
export const mapCursors = Object.fromEntries(
  Object.entries(paths).map(([kind, path]) => [
    kind,
    `url("data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="-3 -3 30 30"><g fill="none" stroke="white" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">${path}</g><g fill="none" stroke="${kind === 'install' ? '#14654b' : '#644c8e'}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${path}</g></svg>`)}") 12 12, pointer`,
  ])
) as Record<MapCursor, string>;
export function scenePointer(event: ThreeEvent<PointerEvent>, kind: MapCursor) {
  event.stopPropagation();
  const canvas = event.nativeEvent.target;
  if (canvas instanceof HTMLCanvasElement)
    canvas.style.cursor = event.buttons ? 'grabbing' : mapCursors[kind];
}
export function clearScenePointer(event: ThreeEvent<PointerEvent>) {
  const canvas = event.nativeEvent.target;
  if (canvas instanceof HTMLCanvasElement) canvas.style.cursor = 'grab';
}
