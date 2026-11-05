import { describe, expect, it, vi } from 'vitest';
import { createAccountApi } from '../src/accounts/api';
import { createAccountFlow } from '../src/accounts/flow';
import { createAccountLink } from '../src/accounts/fragment';
import type { AccessSession } from '../src/accounts/types';
import type { HistoryExport } from '../src/api/types';
import { IdentityManager, type IdentityView } from '../src/storage/identity';

const owner: IdentityView = { id: 'owner-one', kind: 'account', owner_ids: ['owner-one'] };
const otherOwner: IdentityView = { id: 'owner-two', kind: 'account', owner_ids: ['owner-two'] };
const guest: IdentityView = { id: 'guest-after-logout', kind: 'guest', owner_ids: ['guest-after-logout'] };
const currentSession: AccessSession = {
  id: 'current-session', created_at: '2026-11-05T10:00:00Z', last_seen_at: '2026-11-05T10:00:00Z',
  expires_at: '2026-12-05T10:00:00Z', current: true, mfa_verified_until: null,
};
const history: HistoryExport = {
  version: '1', exported_at: '2026-11-05T10:00:00Z', profile_id: 'profile-2027',
  sessions: [], assessments: [],
  learning: { algorithm_version: 'v1', annotations: [], reviews: [], corrections: [] }, account: null,
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

type Flow = ReturnType<typeof createAccountFlow>;
const transitions: {
  name: string; path: string; body: string; payload: unknown;
  next: IdentityView; run: (flow: Flow) => Promise<void>;
}[] = [
  { name: 'MFA confirmation', path: '/auth/mfa/confirm', body: '{"code":"000123"}',
    payload: { enabled: true, verified_until: '2026-11-05T10:15:00Z' }, next: owner, run: (flow) => flow.confirmMfa('000123') },
  { name: 'MFA verification', path: '/auth/mfa/verify', body: '{"code":"000123"}',
    payload: { enabled: true, verified_until: '2026-11-05T10:15:00Z' }, next: owner, run: (flow) => flow.verifyMfa('000123') },
  { name: 'logout', path: '/auth/logout', body: '{}', payload: { ok: true }, next: guest, run: (flow) => flow.logout() },
  { name: 'current-session revocation', path: '/account/sessions/current-session/revoke', body: '{}',
    payload: { ok: true }, next: guest, run: (flow) => flow.revokeSession(currentSession) },
];

async function rig(fetcher: typeof fetch) {
  // The resolver is the external identity endpoint, not a stubbed transition implementation.
  let remote = owner;
  const identity = new IdentityManager(async () => remote);
  await identity.refresh();
  const api = createAccountApi(fetcher, identity);
  const flow = createAccountFlow(api, identity, createAccountLink());
  return { identity, api, flow, setRemote: (value: IdentityView) => { remote = value; } };
}

function pauseFirstDrain(identity: IdentityManager) {
  const entered = deferred<void>();
  const drained = deferred<void>();
  let drains = 0;
  const remove = identity.beforeChange(() => {
    if (++drains !== 1) return Promise.resolve();
    entered.resolve();
    return drained.promise;
  });
  return { entered: entered.promise, release: () => drained.resolve(), remove };
}

describe('account transitions through the real identity manager', () => {
  it.each(transitions)('keeps the captured verified owner through the intentional $name drain and transport', async (operation) => {
    const response = deferred<Response>();
    const transported = deferred<void>();
    const fetcher = vi.fn<typeof fetch>().mockImplementation(() => {
      transported.resolve();
      return response.promise;
    });
    const { identity, api, flow, setRemote } = await rig(fetcher);
    const previous = api.captureAccess();
    expect(previous).toEqual({ owner: 'owner-one', epoch: 1 });
    const barrier = pauseFirstDrain(identity);
    const pending = operation.run(flow);
    expect(operation.run(flow), 'Repeated intentional actions coalesce while draining.').toBe(pending);
    await barrier.entered;
    expect(identity.getSnapshot()).toMatchObject({ value: owner, ready: true, changing: true, epoch: previous.epoch });
    expect(fetcher).not.toHaveBeenCalled();
    barrier.release();
    await transported.promise;
    expect(identity.getSnapshot()).toMatchObject({ value: owner, ready: true, changing: true, epoch: previous.epoch });
    expect(fetcher).toHaveBeenCalledExactlyOnceWith(`/api/v1${operation.path}`, expect.objectContaining({
      method: 'POST', credentials: 'same-origin', cache: 'no-store', body: operation.body,
      headers: expect.objectContaining({ 'X-Learning-Owner': previous.owner, 'X-Requested-With': 'math-ege' }),
    }));
    expect(fetcher.mock.calls[0][1]?.signal?.aborted).toBe(false);
    setRemote(operation.next);
    response.resolve(Response.json(operation.payload));
    await expect(pending).resolves.toBeUndefined();
    expect(identity.getSnapshot()).toMatchObject({
      value: operation.next, ready: true, changing: false, error: null,
      epoch: operation.next.kind === 'guest' ? 2 : 1,
    });
    expect(flow.getSnapshot()).toMatchObject({ action: null, error: null });
    barrier.remove();
  });

  describe.each(['unrelated owner', 'same owner with a newer epoch'] as const)('a changed %s during draining', (change) => {
    it.each(transitions)('rejects $name before transport instead of recapturing access after the drain', async (operation) => {
      const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json(operation.payload));
      const { identity, api, flow, setRemote } = await rig(fetcher);
      const previous = api.captureAccess();
      const barrier = pauseFirstDrain(identity);
      const pending = operation.run(flow);
      const rejected = expect(pending).rejects.toMatchObject({ status: 409, code: 'conflict' });
      await barrier.entered;
      expect(identity.getSnapshot()).toMatchObject({ value: owner, ready: true, changing: true, epoch: previous.epoch });
      expect(fetcher).not.toHaveBeenCalled();
      // Public refresh models an unrelated cookie/access change while the original barrier is still deferred.
      setRemote(otherOwner);
      await identity.refresh();
      if (change === 'same owner with a newer epoch') {
        setRemote(owner);
        await identity.refresh();
        expect(identity.current()).toBe(previous.owner);
      } else expect(identity.current()).toBe('owner-two');
      expect(identity.getSnapshot().epoch).toBe(change === 'same owner with a newer epoch' ? 3 : 2);
      barrier.release();
      await rejected;
      expect(fetcher, 'An old intent must not be sent under newly captured owner/epoch access.').not.toHaveBeenCalled();
      expect(identity.getSnapshot()).toMatchObject({ ready: true, changing: false, error: null });
      expect(flow.getSnapshot()).toMatchObject({ action: null, error: expect.any(String) });
      barrier.remove();
    });
  });

  it('latches a same-owner, same-epoch intervening transition even when the deferred export transport ignores abort', async () => {
    const response = deferred<Response>();
    // Deliberately ignore AbortSignal, as a response already being delivered may do.
    const fetcher = vi.fn<typeof fetch>().mockReturnValue(response.promise);
    const { identity, api } = await rig(fetcher);
    const previous = api.captureAccess();
    const pending = api.exportHistory();
    const rejected = expect(pending).rejects.toMatchObject({ status: 409, code: 'conflict' });
    const barrier = pauseFirstDrain(identity);
    const changing = identity.transition(async () => undefined);
    await barrier.entered;
    expect(identity.getSnapshot().changing).toBe(true);
    expect(fetcher.mock.calls[0][1]?.signal?.aborted).toBe(true);
    barrier.release();
    await changing;
    expect(api.captureAccess()).toEqual(previous);
    expect(identity.getSnapshot().changing).toBe(false);
    response.resolve(Response.json(history));
    await rejected;
    expect(fetcher).toHaveBeenCalledOnce();
    barrier.remove();
  });
});
