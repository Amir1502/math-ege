(function () {
  var supported = 'noModule' in document.createElement('script')
    && typeof BigInt === 'function'
    && typeof Promise === 'function'
    && typeof Map === 'function'
    && typeof Set === 'function'
    && typeof URL === 'function'
    && typeof URLSearchParams === 'function'
    && typeof TextDecoder === 'function'
    && typeof window.fetch === 'function'
    && window.crypto
    && typeof window.crypto.getRandomValues === 'function'
    && window.crypto.subtle
    && typeof window.crypto.subtle.digest === 'function';
  document.documentElement.setAttribute('data-offline-supported', supported ? 'true' : 'false');
  document.getElementById('root').hidden = !supported;
  document.getElementById('offline-compatibility').hidden = !!supported;
}());
