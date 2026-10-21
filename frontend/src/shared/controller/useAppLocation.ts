import { useSyncExternalStore, type MouseEvent } from 'react';
const current = () => window.location.pathname + window.location.search + window.location.hash;
const subscribe = (listener: () => void) => {
  window.addEventListener('popstate', listener);
  window.addEventListener('hashchange', listener);
  return () => {
    window.removeEventListener('popstate', listener);
    window.removeEventListener('hashchange', listener);
  };
};
export function navigate(path: string, replace = false) {
  const url = new URL(path, window.location.origin);
  if (url.origin !== window.location.origin) return;
  const destination = url.pathname + url.search + url.hash;
  if (destination === current()) {
    if (url.hash)
      document
        .getElementById(url.hash.slice(1))
        ?.scrollIntoView({ block: 'start', behavior: 'instant' });
    else window.scrollTo({ top: 0, behavior: 'instant' });
    return;
  }
  window.history[replace ? 'replaceState' : 'pushState'](null, '', destination);
  window.dispatchEvent(new PopStateEvent('popstate'));
}
export function followLink(event: MouseEvent<HTMLAnchorElement>, path: string) {
  if (event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  navigate(path);
}
export function useAppLocation() {
  return useSyncExternalStore(subscribe, current, () => '/');
}
