const motionTargets = [
  '.home-hero-copy > *',
  '.home-hero-art',
  '.home-section-heading',
  '.home-guide',
  '.home-mode > .home-game-image',
  '.home-mode-copy',
  '.home-seoul-toolbar',
  '.home-seoul-view > .home-game-image',
  '.home-street-story > *',
  '.home-shared-story > *',
  '.home-facility-picker',
  '.home-facility-detail',
  '.home-feature-grid > article',
  '.home-score-formula',
  '.home-score-example',
  '.home-score-modes > article',
  '.home-score-rules',
  '.home-competition-gallery > .home-game-image',
  '.home-competitions > .home-story-copy',
  '.data-section-heading',
  '.data-source-grid > article',
  '.home-data > section > h3',
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
            const image = element.matches('.home-game-image, .home-hero-art');
            const copy = element.matches('.home-mode-copy, .home-story-copy');
            const x = copy ? (sibling === 0 ? -14 : 14) : 0;
            const animation = element.animate(
              [
                {
                  opacity: 0,
                  transform: `translate3d(${x}px, ${image ? 32 : 18}px, 0) scale(${image ? 0.975 : 1})`,
                },
                { opacity: 1, transform: 'translate3d(0, 0, 0) scale(1)' },
              ],
              {
                duration: image ? 760 : 580,
                delay: Math.min(Math.max(sibling, 0), 2) * 55,
                easing: 'cubic-bezier(0.16, 1, 0.3, 1)',
                fill: 'backwards',
              }
            );
            animations.set(element, animation);
            animation.onfinish = () => {
              if (animations.get(element) === animation) animations.delete(element);
            };
          }
        }
        const animation = animations.get(element);
        if (!entry.isIntersecting || document.hidden) animation?.pause();
        else animation?.play();
      }
    },
    { threshold: 0.08, rootMargin: '0px 0px 48px 0px' }
  );
  const resetObserver = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        const element = entry.target as HTMLElement;
        // 화면 경계의 작은 왕복에는 반복하지 않고 충분히 벗어난 뒤 다시 등장시킨다.
        if (!entry.isIntersecting && !element.contains(document.activeElement)) {
          seen.delete(element);
          cancel(element);
        }
      }
    },
    { rootMargin: '240px 0px', threshold: 0 }
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
  elements.forEach((element) => {
    observer.observe(element);
    resetObserver.observe(element);
  });
  visibility();
  document.addEventListener('visibilitychange', visibility);
  media.addEventListener('change', preference);
  root.addEventListener('focusin', focus);
  return () => {
    observer.disconnect();
    resetObserver.disconnect();
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
