import { AccountError, accountErrorText } from './errors';
import type { AccountLink } from './fragment';
import type { Account, AccountAuthApi, AccountRequestAccess, AccessSession, AuthConfig, IdentityTransition, LinkRequest, MfaEnrollment } from './types';
import { normalizeMfaCode } from './validation';

interface FlowState {
  action: string | null;
  lastAction: string | null;
  error: string | null;
  completionRecovery: 'none' | 'check' | 'current';
}

export function createAccountFlow(api: AccountAuthApi, identity: IdentityTransition, link: AccountLink) {
  let active: { name: string; promise: Promise<void> } | null = null;
  let state: FlowState = { action: null, lastAction: null, error: null, completionRecovery: 'none' };
  const listeners = new Set<() => void>();
  let setup: { owner: string; value: MfaEnrollment } | null = null;
  let secretGeneration = 0;
  let expectedCompletion: Account | null = null;

  const publish = (next: FlowState) => { state = next; listeners.forEach((listener) => listener()); };
  const forgetEnrollment = () => { setup = null; secretGeneration += 1; publish({ ...state }); };
  const discardCompletion = () => {
    link.discard(); expectedCompletion = null;
    publish({ ...state, completionRecovery: 'none', error: state.lastAction === 'complete' ? null : state.error });
  };

  function transitionAccount(action: (access: AccountRequestAccess) => Promise<unknown>): Promise<void> {
    // Capture before quiescing: a cookie/owner change while barriers drain must not retarget the action.
    const access = api.captureAccess();
    return identity.transition(() => action(access));
  }

  function once(name: string, action: () => Promise<void>): Promise<void> {
    if (active) return active.name === name ? active.promise : Promise.reject(new AccountError(409, 'action_in_progress'));
    publish({ ...state, action: name, lastAction: name, error: null });
    const promise = Promise.resolve().then(action).then(
      () => { publish({ ...state, action: null, lastAction: name, error: null }); },
      (error: unknown) => { publish({ ...state, action: null, lastAction: name, error: accountErrorText(error) }); throw error; },
    ).finally(() => { active = null; });
    active = { name, promise };
    return promise;
  }

  function matchesIdentity(account: Account): boolean {
    const access = identity.getSnapshot();
    return access.ready && !access.changing && !access.error && access.value?.kind === 'account'
      && access.value.id === account.root_guest_id && account.email_verified;
  }

  async function readCompletion(): Promise<boolean> {
    const access = identity.getSnapshot();
    if (!access.ready || access.changing || access.error) throw new AccountError(0, 'completion_unconfirmed');
    const account = await api.current();
    const resolved = identity.getSnapshot();
    if (!resolved.ready || resolved.changing || resolved.error) throw new AccountError(0, 'completion_unconfirmed');
    if (!account) {
      if (expectedCompletion || resolved.value?.kind === 'account') throw new AccountError(0, 'completion_unconfirmed');
      return false;
    }
    if (!matchesIdentity(account) || (expectedCompletion && expectedCompletion.id !== account.id)) {
      throw new AccountError(0, 'completion_unconfirmed');
    }
    return true;
  }

  function checkCompletion(): Promise<void> {
    return once('complete', async () => {
      await identity.refresh();
      let confirmed: boolean;
      try { confirmed = await readCompletion(); }
      catch { throw new AccountError(0, 'completion_unconfirmed'); }
      if (!confirmed) {
        publish({ ...state, completionRecovery: 'none' });
        throw new AccountError(0, 'login_not_confirmed');
      }
      link.discard(); expectedCompletion = null;
      publish({ ...state, completionRecovery: 'current' });
      forgetEnrollment();
    });
  }

  function complete(): Promise<void> {
    if (state.completionRecovery === 'check') return checkCompletion();
    return once('complete', async () => {
      expectedCompletion = null;
      publish({ ...state, completionRecovery: 'none' });
      await link.submit(async (body) => {
        try {
          await identity.transition(async () => { expectedCompletion = await api.complete(body); });
          if (expectedCompletion && matchesIdentity(expectedCompletion)) return;
        } catch (error) {
          if (!expectedCompletion && error instanceof AccountError && !error.retryable) throw error;
        }
        // A link is single-use. A lost response is reconciled through identity + GET /account,
        // never an automatic second POST. A received AccountView also pins the expected account.
        publish({ ...state, completionRecovery: 'check' });
        try {
          if (await readCompletion()) { publish({ ...state, completionRecovery: 'current' }); return; }
        } catch { /* Keep the read-only recovery prompt until access can be established. */ }
        throw new AccountError(0, 'completion_unconfirmed');
      });
      expectedCompletion = null;
      forgetEnrollment();
    });
  }

  function mfa(code: string, enrollment: boolean): Promise<void> {
    let value: string;
    try { value = normalizeMfaCode(code); }
    catch (error) { return Promise.reject(error); }
    return once(enrollment ? 'mfa-confirm' : 'mfa-verify', async () => {
      await transitionAccount((access) => enrollment ? api.confirmMfa(value, access) : api.verifyMfa(value, access));
      forgetEnrollment();
    });
  }

  return {
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    getSnapshot: () => state,
    clearError: () => publish({ ...state, error: null }),
    forgetEnrollment,
    discardCompletion,
    enrollment: (owner: string): MfaEnrollment | null => {
      if (setup && Date.parse(setup.value.expires_at) <= Date.now()) setup = null;
      return setup?.owner === owner ? setup.value : null;
    },
    enrollMfa: (owner: string) => once('mfa-enroll', async () => {
      const generation = secretGeneration;
      const value = await api.enrollMfa();
      if (generation === secretGeneration) setup = { owner, value };
    }),
    requestLink: (config: AuthConfig, body: LinkRequest): Promise<void> => {
      if (!config.enabled) return Promise.reject(new AccountError(503, 'accounts_disabled'));
      if (!body.accept_policy || !config.policy_version || body.policy_version !== config.policy_version) {
        return Promise.reject(new AccountError(422, 'consent_required'));
      }
      return api.requestLink(body);
    },
    complete,
    logout: () => once('logout', async () => {
      await transitionAccount((access) => api.logout(access));
      forgetEnrollment();
      discardCompletion();
    }),
    confirmMfa: (code: string) => mfa(code, true),
    verifyMfa: (code: string) => mfa(code, false),
    revokeSession: (session: AccessSession) => session.current
      ? once(`revoke:${session.id}`, async () => {
        await transitionAccount((access) => api.revokeSession(session.id, access));
        forgetEnrollment();
        discardCompletion();
      })
      : api.revokeSession(session.id),
  };
}
