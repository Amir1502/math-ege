import { AccountError } from './errors';
import type { LinkComplete } from './types';

type LinkLocation = Pick<Location, 'pathname' | 'search' | 'hash'>;
type LinkHistory = Pick<History, 'replaceState'>;
export type CompletionState = 'empty' | 'ready' | 'invalid';

const completionRoute = '/#/auth/complete';
const maximumLifetime = 15 * 60 * 1000;

export function createAccountLink(now = () => Date.now()) {
  let state: CompletionState = 'empty';
  let pending: { body: LinkComplete; expiresAt: number } | null = null;
  let expiry: number | null = null;

  const discard = () => {
    pending = null; state = 'empty';
    if (expiry !== null) window.clearTimeout(expiry);
    expiry = null;
  };
  const status = (): CompletionState => {
    if (pending && pending.expiresAt <= now()) { discard(); state = 'invalid'; }
    return state;
  };

  return {
    status,
    discard,
    capture(location: LinkLocation, history: LinkHistory): CompletionState {
      const completionPath = location.pathname === '/auth/complete' || location.pathname === '/account';
      const tokenFragment = /^#token(?:=|&|$)/.test(location.hash);
      if (!completionPath && !tokenFragment) return status();

      // Erase before parsing, validation or any asynchronous work. No history.state copy.
      const fragment = location.hash;
      const hasQuery = location.search.length > 0;
      discard();
      state = 'invalid';
      try { history.replaceState(null, '', completionRoute); }
      catch { return state; }
      if (!completionPath || hasQuery || fragment.length > 300) return state;

      const values = new URLSearchParams(fragment.slice(1));
      const token = values.get('token');
      if ([...values.keys()].length !== 1 || !token || !/^[A-Za-z0-9_-]{43}$/.test(token)) return state;
      pending = { body: Object.freeze({ token }), expiresAt: now() + maximumLifetime };
      state = 'ready';
      if (typeof window !== 'undefined') expiry = window.setTimeout(() => { discard(); state = 'invalid'; }, maximumLifetime);
      return state;
    },
    async submit(action: (body: LinkComplete) => Promise<void>): Promise<void> {
      if (status() !== 'ready' || !pending) throw new AccountError(400, 'invalid_link');
      const request = pending;
      try {
        await action(request.body);
        if (pending === request) discard();
      } catch (error) {
        // Keep an uncertain intent in memory while read-only account recovery runs.
        if (error instanceof AccountError && !error.retryable && pending === request) {
          discard();
          state = 'invalid';
        }
        throw error;
      }
    },
  };
}

export type AccountLink = ReturnType<typeof createAccountLink>;
export const accountLink = createAccountLink();

let listening = false;
export function captureAccountLink(): CompletionState {
  if (typeof window === 'undefined') return accountLink.status();
  const result = accountLink.capture(window.location, window.history);
  if (!listening) {
    listening = true;
    window.addEventListener('pagehide', accountLink.discard);
    window.addEventListener('hashchange', () => {
      if (window.location.hash !== '#/auth/complete') accountLink.discard();
    });
  }
  return result;
}

// Eagerly import this module before routing/telemetry. It has no storage, fetch or identity side effects.
captureAccountLink();
