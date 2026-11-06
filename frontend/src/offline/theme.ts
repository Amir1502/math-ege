import { useLayoutEffect, useState, useSyncExternalStore } from 'react';

type Theme = 'light' | 'dark';
const storageKey = 'math-ege-offline-theme-v1';
const systemQuery = '(prefers-color-scheme: dark)';

function savedTheme(): Theme | null {
  try {
    const value = window.localStorage.getItem(storageKey);
    return value === 'light' || value === 'dark' ? value : null;
  } catch {
    return null;
  }
}

function systemTheme(): Theme {
  return typeof window.matchMedia === 'function' && window.matchMedia(systemQuery).matches ? 'dark' : 'light';
}

function subscribeSystemTheme(onChange: () => void) {
  if (typeof window.matchMedia !== 'function') return () => {};
  const query = window.matchMedia(systemQuery);
  if (typeof query.addEventListener === 'function') {
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }
  query.addListener(onChange);
  return () => query.removeListener(onChange);
}

export function useOfflineTheme() {
  const [preference, setPreference] = useState(savedTheme);
  const system = useSyncExternalStore(subscribeSystemTheme, systemTheme);
  const theme = preference ?? system;

  useLayoutEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = theme;
    const canvas = window.getComputedStyle(root).getPropertyValue('--canvas').trim();
    document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.setAttribute('content', canvas);
  }, [theme]);

  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    setPreference(next);
    try {
      window.localStorage.setItem(storageKey, next);
    } catch {
      // Keep the selected theme for this launch even when preferences cannot be saved.
    }
  };

  return { theme, toggleTheme };
}
