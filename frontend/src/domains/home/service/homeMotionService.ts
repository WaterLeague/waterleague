const motionTargets = [
  '.home-hero-copy > *',
  '.home-hero-art',
  '.home-section-heading',
  '.home-guide',
  '.home-mode',
  '.home-seoul-view',
  '.home-street-story',
  '.home-shared-story',
  '.home-facility-picker',
  '.home-facility-detail',
  '.home-feature-grid > article',
  '.home-start',
  '.data-section-heading',
].join(',');

export function startHomeMotion(root: HTMLElement): () => void {
  if (!window.matchMedia || !('IntersectionObserver' in window)) return () => {};
  const media = window.matchMedia('(prefers-reduced-motion: reduce)');
  const elements = [...root.querySelectorAll<HTMLElement>(motionTargets)];
  const seen = new Set<HTMLElement>();
  const animations = new Map<HTMLElement, Animation>();
  const cancel = (element: HTMLElement) => {
    animations.get(element)?.cancel();
    animations.delete(element);
  };
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        const element = entry.target as HTMLElement;
        element.dataset.homeActive = String(entry.isIntersecting);
        if (entry.isIntersecting && !seen.has(element)) {
          seen.add(element);
          if (!media.matches && element.animate) {
            const sibling = [...(element.parentElement?.children ?? [])].indexOf(element);
            const animation = element.animate(
              [
                { opacity: 0, transform: 'translate3d(0, 24px, 0)' },
                { opacity: 1, transform: 'translate3d(0, 0, 0)' },
              ],
              {
                duration: 700,
                delay: Math.min(Math.max(sibling, 0), 3) * 65,
                easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
                fill: 'backwards',
              }
            );
            animations.set(element, animation);
            animation.onfinish = () => animations.delete(element);
          }
        }
        const animation = animations.get(element);
        if (!entry.isIntersecting || document.hidden) animation?.pause();
        else animation?.play();
      }
    },
    { threshold: 0.06 }
  );
  const visibility = () => {
    root.dataset.motionPaused = String(document.hidden);
    for (const [element, animation] of animations) {
      if (document.hidden || element.dataset.homeActive !== 'true') animation.pause();
      else animation.play();
    }
  };
  const preference = () => {
    if (media.matches) for (const element of animations.keys()) cancel(element);
  };
  const focus = (event: FocusEvent) => {
    // 키보드로 이동한 항목은 등장 지연 없이 즉시 읽을 수 있어야 한다.
    for (const element of elements) {
      if (event.target instanceof Node && element.contains(event.target)) {
        seen.add(element);
        cancel(element);
      }
    }
  };
  elements.forEach((element) => observer.observe(element));
  visibility();
  document.addEventListener('visibilitychange', visibility);
  media.addEventListener('change', preference);
  root.addEventListener('focusin', focus);
  return () => {
    observer.disconnect();
    document.removeEventListener('visibilitychange', visibility);
    media.removeEventListener('change', preference);
    root.removeEventListener('focusin', focus);
    for (const element of elements) {
      cancel(element);
      delete element.dataset.homeActive;
    }
    delete root.dataset.motionPaused;
  };
}
