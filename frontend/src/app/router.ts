import { useSyncExternalStore } from 'react';

function subscribe(callback: () => void) {
  window.addEventListener('hashchange', callback);
  return () => window.removeEventListener('hashchange', callback);
}

function snapshot() { return window.location.hash.slice(1) || '/'; }

export function useRoute() {
  const location = useSyncExternalStore(subscribe, snapshot);
  const [path, query] = location.split('?');
  return { path, query: new URLSearchParams(query), location };
}

export function navigate(path: string) { window.location.hash = path; }

export function sessionPath(id: string) { return `/session/${encodeURIComponent(id)}`; }
