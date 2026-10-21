import { useSyncExternalStore, type MouseEvent } from 'react';
const current = () => window.location.pathname + window.location.search;
const subscribe = (listener: () => void) => {
  window.addEventListener('popstate', listener);
  return () => window.removeEventListener('popstate', listener);
};
export function navigate(path: string, replace = false) {
  const url = new URL(path, window.location.origin);
  if (url.origin !== window.location.origin) return;
  window.history[replace ? 'replaceState' : 'pushState'](null, '', url.pathname + url.search);
  window.dispatchEvent(new PopStateEvent('popstate'));
}
export function followLink(event: MouseEvent<HTMLAnchorElement>, path: string) {
  if (event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  navigate(path);
}
export function useAppLocation() {
  return useSyncExternalStore(subscribe, current, () => '/weekly');
}
