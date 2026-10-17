export function watchContextLoss(target: EventTarget, onUnavailable: () => void) {
  let lost = false;
  function onLoss(event: Event) {
    event.preventDefault();
    if (!lost) {
      lost = true;
      onUnavailable();
    }
  }
  target.addEventListener('webglcontextlost', onLoss);
  return () => target.removeEventListener('webglcontextlost', onLoss);
}
