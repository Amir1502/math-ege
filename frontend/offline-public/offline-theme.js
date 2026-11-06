(function () {
  var theme = null;
  try {
    theme = window.localStorage.getItem('math-ege-offline-theme-v1');
  } catch {
    // Preferences are optional; unavailable storage must not prevent startup.
  }
  if (theme !== 'light' && theme !== 'dark') {
    theme = typeof window.matchMedia === 'function' && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  document.documentElement.setAttribute('data-theme', theme);
}());
