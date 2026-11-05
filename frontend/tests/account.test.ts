import { randomBytes } from 'node:crypto';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createAccountApi as createApi, emailResponseMessage } from '../src/accounts/api';
import { AccountError, accountErrorText } from '../src/accounts/errors';
import { createAccountLink } from '../src/accounts/fragment';
import { createAccountFlow } from '../src/accounts/flow';
import { hasRecentMfa, normalizeEmail, normalizeMfaCode, safePolicyUrl } from '../src/accounts/validation';
import type { Account, AccountApi, AccountIdentityAccess, AccessSession, AuthConfig, DeletionRequest, IdentityTransition } from '../src/accounts/types';

const account: Account = {
  id: 'account-one', email: 'student@example.org', email_verified: true, role: 'student',
  root_guest_id: 'owner-one', owner_ids: ['owner-one', 'claimed-guest'],
  created_at: '2026-11-05T10:00:00Z', policy_version: '2026-11', consented_at: '2026-11-05T10:00:00Z',
  daily_minutes: 20, mfa_enabled: false, mfa_verified_until: null,
};
const config: AuthConfig = {
  enabled: true, policy_version: '2026-11', policy_url: 'https://example.org/privacy',
  link_ttl_seconds: 900,
};
const session: AccessSession = {
  id: 'session-one', created_at: account.created_at, last_seen_at: account.created_at,
  expires_at: '2026-12-05T10:00:00Z', current: true, mfa_verified_until: null,
};
const requestedDeletion: DeletionRequest = {
  id: '11111111-1111-4111-8111-111111111111', status: 'requested', requested_at: account.created_at,
  deadline_at: '2026-12-05T10:00:00Z',
};
const emptyExport = {
  version: '1', exported_at: account.created_at, profile_id: 'profile-one', sessions: [], assessments: [],
  learning: { algorithm_version: 'v1', annotations: [], reviews: [], corrections: [] }, account: null,
};
const scopedRequests: [string, (api: AccountApi) => Promise<unknown>, unknown][] = [
  ['current account', (api) => api.current(), account],
  ['settings', (api) => api.updateSettings({ daily_minutes: 30 }), account],
  ['sessions', (api) => api.sessions(), { sessions: [session] }],
  ['deletion status', (api) => api.deletionStatus(), { request: requestedDeletion }],
  ['deletion request', (api) => api.requestDeletion(true), { request: requestedDeletion }],
  ['deletion cancellation', (api) => api.cancelDeletion(requestedDeletion.id), { ...requestedDeletion, status: 'canceled', canceled_at: '2026-11-05T10:05:00Z' }],
  ['logout', (api) => api.logout(), { ok: true }],
  ['session revocation', (api) => api.revokeSession(session.id), { ok: true }],
  ['MFA enrollment', (api) => api.enrollMfa(), { provisioning_uri: 'otpauth://totp/Exam?secret=ABCDEFGHIJKLMNOPQRSTUVWXYZ234567', expires_at: '2026-11-05T10:10:00Z' }],
  ['MFA confirmation', (api) => api.confirmMfa('000123'), { enabled: true, verified_until: '2026-11-05T10:15:00Z' }],
  ['MFA verification', (api) => api.verifyMfa('000123'), { enabled: true, verified_until: '2026-11-05T10:15:00Z' }],
  ['export', (api) => api.exportHistory(), emptyExport],
];
function browser(url: string) {
  let current = new URL(url);
  return {
    get location() { return current; },
    history: { replaceState: vi.fn((_state: unknown, _unused: string, next?: string | URL | null) => {
      current = new URL(String(next), current);
    }) },
  };
}
function transition(current: Account | null = account) {
  const access = identityAccess(current);
  return {
    ...access,
    transition: vi.fn<IdentityTransition['transition']>(async (action) => {
      access.update({ changing: true });
      try { await action(); }
      finally { access.update({ changing: false }); }
    }),
    refresh: vi.fn(async () => undefined),
  };
}

function identityAccess(current: Account | null = account) {
  let snapshot = {
    value: current ? { id: current.root_guest_id, kind: 'account' as 'account' | 'guest' } : null,
    ready: true, changing: false, error: null as string | null, epoch: 1,
  };
  const listeners = new Set<() => void>();
  return {
    getSnapshot: () => snapshot,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    update: (change: Partial<typeof snapshot>) => {
      snapshot = { ...snapshot, ...change };
      listeners.forEach((listener) => listener());
    },
    listeners,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

function createAccountApi(fetcher: typeof fetch, access: AccountIdentityAccess = identityAccess()) {
  return createApi(fetcher, access);
}

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('account request ownership', () => {
  it('rejects a late successful settings response from the previous owner', async () => {
    const access = identityAccess();
    const response = deferred<Response>();
    const fetcher = vi.fn<typeof fetch>().mockReturnValue(response.promise);
    const api = createAccountApi(fetcher, access);
    const saving = api.updateSettings({ daily_minutes: 30 });
    access.update({ value: { id: 'owner-two', kind: 'account' }, epoch: 2 });
    response.resolve(Response.json({ ...account, daily_minutes: 30 }));
    await expect(saving).rejects.toMatchObject({ status: 409, code: 'conflict' });
    expect(fetcher.mock.calls[0][1]?.headers).toMatchObject({ 'X-Learning-Owner': 'owner-one' });
    expect(access.listeners.size).toBe(0);
  });

  it('pins the previous verified owner while an intentional logout transition is still changing', async () => {
    const identities = transition();
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => {
      expect(identities.getSnapshot().changing).toBe(true);
      return Response.json({ ok: true });
    });
    const flow = createAccountFlow(createAccountApi(fetcher, identities), identities, createAccountLink());
    await expect(flow.logout()).resolves.toBeUndefined();
    expect(fetcher.mock.calls[0][1]?.headers).toMatchObject({ 'X-Learning-Owner': 'owner-one' });
    expect(identities.getSnapshot().changing).toBe(false);
  });

  it.each(scopedRequests)('pins verified canonical access on each %s request', async (_name, request, payload) => {
    const access = identityAccess();
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json(payload));
    await request(createAccountApi(fetcher, access));
    expect(fetcher.mock.calls[0][1]).toMatchObject({
      credentials: 'same-origin', cache: 'no-store', redirect: 'error',
      headers: { 'X-Learning-Owner': 'owner-one' },
    });
    expect(access.listeners.size).toBe(0);
  });

  it.each([
    ['unverified', { ready: false }], ['changing', { changing: true }],
    ['uncertain', { error: 'Unconfirmed access' }], ['absent', { value: null }],
  ] as const)('blocks ordinary scoped requests before transport when owner access is %s', async (_name, change) => {
    const access = identityAccess();
    access.update(change);
    const fetcher = vi.fn<typeof fetch>();
    const api = createAccountApi(fetcher, access);
    for (const [name, request] of scopedRequests) {
      if (name !== 'current account') await expect(request(api)).rejects.toMatchObject({ code: 'conflict' });
    }
    expect(fetcher).not.toHaveBeenCalled();
    expect(access.listeners.size).toBe(0);
  });

  it.each(scopedRequests)('rejects a late %s response even after a same-owner transition has finished', async (_name, request, payload) => {
    const access = identityAccess();
    const response = deferred<Response>();
    const fetcher = vi.fn<typeof fetch>().mockReturnValue(response.promise);
    const pending = request(createAccountApi(fetcher, access));
    access.update({ changing: true });
    expect(fetcher.mock.calls[0][1]?.signal?.aborted).toBe(true);
    access.update({ changing: false });
    response.resolve(Response.json(payload));
    await expect(pending).rejects.toMatchObject({ status: 409, code: 'conflict' });
    expect(access.listeners.size).toBe(0);
  });

  it('captures the new verified owner per call instead of retaining the factory owner', async () => {
    const access = identityAccess();
    const other = { ...account, id: 'account-two', root_guest_id: 'owner-two', owner_ids: ['owner-two'] };
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json(other));
    const api = createAccountApi(fetcher, access);
    access.update({ value: { id: 'owner-two', kind: 'account' }, epoch: 2 });
    await expect(api.updateSettings({ daily_minutes: 20 })).resolves.toEqual(other);
    expect(fetcher.mock.calls[0][1]?.headers).toMatchObject({ 'X-Learning-Owner': 'owner-two' });
  });

  it('checks ownership again after a response body finishes reading', async () => {
    const access = identityAccess();
    const body = deferred<unknown>();
    const response = Response.json(account);
    const reading = vi.spyOn(response, 'json').mockReturnValue(body.promise);
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response);
    const pending = createAccountApi(fetcher, access).current();
    await vi.waitFor(() => expect(reading).toHaveBeenCalled());
    access.update({ epoch: 2 });
    body.resolve(account);
    await expect(pending).rejects.toMatchObject({ code: 'conflict' });
    expect(access.listeners.size).toBe(0);
  });

  it('rejects a different account response even before a changed cookie is observed locally', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ ...account, root_guest_id: 'owner-two' }));
    await expect(createAccountApi(fetcher).current()).rejects.toMatchObject({ code: 'conflict' });
  });

  it.each([
    { ready: false }, { error: 'Unconfirmed access' }, { epoch: 2 },
    { value: { id: 'owner-two', kind: 'account' as const } },
  ])('latches temporary access loss even when the original snapshot is restored', async (change) => {
    const access = identityAccess();
    const response = deferred<Response>();
    const pending = createAccountApi(vi.fn<typeof fetch>().mockReturnValue(response.promise), access).sessions();
    const original = access.getSnapshot();
    access.update(change);
    access.update(original);
    response.resolve(Response.json({ sessions: [session] }));
    await expect(pending).rejects.toMatchObject({ code: 'conflict' });
  });

  it('does not turn a stale unauthorized response into an absent account', async () => {
    const access = identityAccess();
    const response = deferred<Response>();
    const pending = createAccountApi(vi.fn<typeof fetch>().mockReturnValue(response.promise), access).current();
    access.update({ epoch: 2 });
    response.resolve(Response.json({ error: { code: 'account_required' } }, { status: 401 }));
    await expect(pending).rejects.toMatchObject({ code: 'conflict' });
  });

  it('allows a minimal absent-account bootstrap read but never pins an unverified cached owner', async () => {
    const access = identityAccess();
    access.update({ ready: false });
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ error: { code: 'account_required' } }, { status: 401 }));
    await expect(createAccountApi(fetcher, access).current()).resolves.toBeNull();
    expect(fetcher).toHaveBeenCalledOnce();
    expect(fetcher.mock.calls[0][1]?.headers).not.toHaveProperty('X-Learning-Owner');
  });

  it('never returns account PII from an unverified bootstrap read', async () => {
    const access = identityAccess();
    access.update({ ready: false });
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json(account));
    const error: unknown = await createAccountApi(fetcher, access).current().catch((error: unknown) => error);
    expect(error).toMatchObject({ code: 'conflict' });
    expect(JSON.stringify(error)).not.toContain(account.email);
  });

  it.each([{ changing: true }, { error: 'Unconfirmed access' }])('rejects an unsafe bootstrap read before fetching', async (change) => {
    const access = identityAccess(null);
    access.update(change);
    const fetcher = vi.fn<typeof fetch>();
    await expect(createAccountApi(fetcher, access).current()).rejects.toMatchObject({ code: 'conflict' });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('rejects bootstrap data when identity verification finishes during the read', async () => {
    const access = identityAccess();
    access.update({ ready: false });
    const response = deferred<Response>();
    const pending = createAccountApi(vi.fn<typeof fetch>().mockReturnValue(response.promise), access).current();
    access.update({ ready: true });
    response.resolve(Response.json(account));
    await expect(pending).rejects.toMatchObject({ code: 'conflict' });
  });

  it('keeps configuration, request-link and complete bootstrap-exempt without exposing them to owner retargeting', async () => {
    const access = identityAccess(null);
    access.update({ ready: false, changing: true, error: 'Unconfirmed access' });
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json(config))
      .mockResolvedValueOnce(Response.json({ message: 'Generic acknowledgment' }))
      .mockResolvedValueOnce(Response.json(account));
    const api = createAccountApi(fetcher, access);
    await api.config();
    await api.requestLink({ email: account.email, policy_version: config.policy_version!, accept_policy: true });
    await api.complete({ token: randomBytes(32).toString('base64url') });
    for (const [, request] of fetcher.mock.calls) expect(request?.headers).not.toHaveProperty('X-Learning-Owner');
    expect(access.listeners.size).toBe(0);
  });

  it.each(['current-session revoke', 'MFA confirm', 'MFA verify'] as const)('preserves a pinned intentional %s transition', async (action) => {
    const identities = transition();
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => {
      expect(identities.getSnapshot().changing).toBe(true);
      return Response.json(action === 'current-session revoke' ? { ok: true } : { enabled: true, verified_until: '2026-11-05T10:15:00Z' });
    });
    const flow = createAccountFlow(createAccountApi(fetcher, identities), identities, createAccountLink());
    if (action === 'current-session revoke') await flow.revokeSession(session);
    else if (action === 'MFA confirm') await flow.confirmMfa('000123');
    else await flow.verifyMfa('000123');
    expect(fetcher.mock.calls[0][1]?.headers).toMatchObject({ 'X-Learning-Owner': 'owner-one' });
    expect(identities.listeners.size).toBe(0);
  });

  it('cannot retarget a transition if the owner changes while identity barriers drain', async () => {
    const identities = transition();
    identities.transition.mockImplementation(async (action) => {
      identities.update({ value: { id: 'owner-two', kind: 'account' }, epoch: 2, changing: true });
      try { await action(); }
      finally { identities.update({ changing: false }); }
    });
    const fetcher = vi.fn<typeof fetch>();
    const flow = createAccountFlow(createAccountApi(fetcher, identities), identities, createAccountLink());
    await expect(flow.logout()).rejects.toMatchObject({ code: 'conflict' });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('rejects a late transition response if its pinned epoch changes before refresh', async () => {
    const identities = transition();
    const response = deferred<Response>();
    const fetcher = vi.fn<typeof fetch>().mockReturnValue(response.promise);
    const flow = createAccountFlow(createAccountApi(fetcher, identities), identities, createAccountLink());
    const pending = flow.verifyMfa('000123');
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledOnce());
    identities.update({ epoch: 2 });
    response.resolve(Response.json({ enabled: true, verified_until: '2026-11-05T10:15:00Z' }));
    await expect(pending).rejects.toMatchObject({ code: 'conflict' });
    expect(identities.listeners.size).toBe(0);
  });
});

describe('account public client', () => {
  it('reads disabled configuration and an absent account without creating a guest', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({ enabled: false, policy_version: null, policy_url: null, link_ttl_seconds: 900 }))
      .mockResolvedValueOnce(Response.json({ error: { code: 'account_required' } }, { status: 401 }));
    const api = createAccountApi(fetcher);
    expect((await api.config()).enabled).toBe(false);
    expect(await api.current()).toBeNull();
    expect(fetcher.mock.calls.map(([path]) => path)).toEqual(['/api/v1/auth/config', '/api/v1/account']);
    for (const [, options] of fetcher.mock.calls) {
      expect(options).toMatchObject({ method: 'GET', credentials: 'same-origin', cache: 'no-store', redirect: 'error' });
    }
  });

  it('fails closed on an enabled configuration without a usable policy', async () => {
    const api = createAccountApi(vi.fn<typeof fetch>().mockResolvedValue(Response.json({ ...config, policy_url: 'javascript:alert(1)' })));
    await expect(api.config()).rejects.toMatchObject({ code: 'invalid_response' });
  });

  it('uses the published policy gate without requiring unsupported minor settings', async () => {
    const api = createAccountApi(vi.fn<typeof fetch>().mockResolvedValue(Response.json(config)));
    expect(await api.config()).toEqual(config);
  });

  it('sends versioned consent with anti-CSRF headers and keeps the email response generic', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ message: 'An untrusted server message with account details' }, { status: 202 }));
    const api = createAccountApi(fetcher);
    await expect(api.requestLink({ email: ' Student@Example.org ', policy_version: '2026-11', accept_policy: true })).resolves.toBeUndefined();
    expect(emailResponseMessage).toBe('Если адрес доступен для входа, письмо со ссылкой отправлено.');
    expect(fetcher).toHaveBeenCalledWith('/api/v1/auth/request-link', expect.objectContaining({
      method: 'POST', credentials: 'same-origin', cache: 'no-store', redirect: 'error',
      headers: expect.objectContaining({ 'Content-Type': 'application/json', 'X-Requested-With': 'math-ege' }),
      body: JSON.stringify({ email: 'student@example.org', policy_version: '2026-11', accept_policy: true }),
    }));
  });

  it('rejects missing consent and malformed email before contacting the server', async () => {
    const fetcher = vi.fn<typeof fetch>();
    const api = createAccountApi(fetcher);
    await expect(api.requestLink({ email: account.email, policy_version: '2026-11', accept_policy: false })).rejects.toMatchObject({ code: 'consent_required' });
    await expect(api.requestLink({ email: 'bad@address', policy_version: '2026-11', accept_policy: true })).rejects.toMatchObject({ code: 'invalid_email' });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('never exposes an arbitrary server error or network exception', async () => {
    const marker = randomBytes(32).toString('base64url');
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({ error: { code: marker, message: marker } }, { status: 500 }))
      .mockRejectedValueOnce(new Error(marker));
    const api = createAccountApi(fetcher);
    for (const expected of ['request_failed', 'network_error']) {
      const error = await api.current().catch((error: unknown) => error);
      expect(error).toMatchObject({ code: expected });
      expect(accountErrorText(error)).not.toContain(marker);
      expect(JSON.stringify(error)).not.toContain(marker);
    }
    expect(accountErrorText(new Error(marker))).not.toContain(marker);
  });

  it('requires explicit deletion confirmation and only sends a request, never fulfillment', async () => {
    const requested = requestedDeletion;
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ request: requested }));
    const api = createAccountApi(fetcher);
    await expect(api.requestDeletion(false)).rejects.toMatchObject({ code: 'confirmation_required' });
    expect(fetcher).not.toHaveBeenCalled();
    expect(await api.requestDeletion(true)).toEqual(requested);
    expect(fetcher).toHaveBeenCalledExactlyOnceWith('/api/v1/account/deletion-request', expect.objectContaining({
      method: 'POST', body: '{"confirm":true}', headers: expect.objectContaining({ 'X-Requested-With': 'math-ege' }),
    }));
  });

  it('does not display a deletion deadline longer than thirty days as a valid receipt', async () => {
    const api = createAccountApi(vi.fn<typeof fetch>().mockResolvedValue(Response.json({ request: {
      ...requestedDeletion, deadline_at: '2026-12-06T10:00:00Z',
    } })));
    await expect(api.deletionStatus()).rejects.toMatchObject({ code: 'invalid_response' });
  });

  it('cancels only the specified deletion UUID and accepts the minimal canceled receipt', async () => {
    const canceled = { ...requestedDeletion, status: 'canceled', canceled_at: '2026-11-05T10:05:00Z' };
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json(canceled));
    const api = createAccountApi(fetcher);
    await expect(api.cancelDeletion(requestedDeletion.id)).resolves.toEqual(canceled);
    expect(fetcher).toHaveBeenCalledExactlyOnceWith(`/api/v1/account/deletion-request/${requestedDeletion.id}/cancel`, expect.objectContaining({
      method: 'POST', body: '{}', headers: expect.objectContaining({
        'X-Requested-With': 'math-ege', 'Content-Type': 'application/json', 'X-Learning-Owner': 'owner-one',
      }),
    }));
  });

  it.each(['', 'deletion-one', '../deletion', `${requestedDeletion.id}/cancel`, '11111111111141118111111111111111'])('rejects an invalid cancellation UUID %s before transport', async (id) => {
    const fetcher = vi.fn<typeof fetch>();
    await expect(createAccountApi(fetcher).cancelDeletion(id)).rejects.toMatchObject({ code: 'invalid_deletion_request' });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it.each([
    { status: 'requested' }, { status: 'completed' }, { id: '22222222-2222-4222-8222-222222222222' },
    { canceled_at: null }, { canceled_at: 'not-a-date' }, { canceled_at: '2026-11-05T09:59:59Z' },
    { requested_at: '2026-11-05T10:00:00' }, { requested_at: '2026-02-30T10:00:00Z' },
    { deadline_at: '2026-11-05T09:59:59Z' }, { deadline_at: '2026-12-05T10:00:01Z' },
    { canceled_at: '2026-11-05T24:00:00Z' }, { secret: 'private-marker' },
  ])('rejects malformed or mismatched cancellation receipts without retaining response data', async (change) => {
    const canceled = { ...requestedDeletion, status: 'canceled', canceled_at: '2026-11-05T10:05:00Z', ...change };
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json(canceled));
    const error: unknown = await createAccountApi(fetcher).cancelDeletion(requestedDeletion.id).catch((error: unknown) => error);
    expect(error).toMatchObject({ code: 'invalid_response' });
    expect(JSON.stringify(error)).not.toContain('private-marker');
  });

  it('requires all five cancellation receipt fields without a nested request envelope', async () => {
    const canceled = { ...requestedDeletion, status: 'canceled', canceled_at: '2026-11-05T10:05:00Z' };
    for (const payload of [{ request: canceled }, { ...requestedDeletion, status: 'canceled' }, null]) {
      const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json(payload));
      await expect(createAccountApi(fetcher).cancelDeletion(requestedDeletion.id)).rejects.toMatchObject({ code: 'invalid_response' });
    }
  });

  it.each([
    ['deadline beyond thirty days', { deadline_at: '2026-12-05T10:00:00.000001Z' }],
    ['cancellation before the request', {
      requested_at: '2026-11-05T10:00:00.123456Z', canceled_at: '2026-11-05T10:00:00.123455Z',
    }],
  ])('rejects a %s even when the difference is only one microsecond', async (_name, change) => {
    const payload = { ...requestedDeletion, status: 'canceled', canceled_at: '2026-11-05T10:05:00Z', ...change };
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json(payload));
    await expect(createAccountApi(fetcher).cancelDeletion(requestedDeletion.id)).rejects.toMatchObject({ code: 'invalid_response' });
  });

  it('accepts valid microsecond timestamps with equivalent timezone offsets', async () => {
    const payload = {
      ...requestedDeletion, status: 'canceled', requested_at: '2026-11-05T10:00:00.123456+03:00',
      deadline_at: '2026-12-05T07:00:00.123456Z', canceled_at: '2026-11-05T07:00:00.123456Z',
    };
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json(payload));
    await expect(createAccountApi(fetcher).cancelDeletion(requestedDeletion.id)).resolves.toEqual(payload);
  });

  it('allows an explicit same-UUID retry to read the already-canceled receipt after an uncertain response', async () => {
    const canceled = { ...requestedDeletion, status: 'canceled', canceled_at: '2026-11-05T10:05:00.123456+00:00' };
    const fetcher = vi.fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError('connection closed'))
      .mockResolvedValueOnce(Response.json(canceled));
    const api = createAccountApi(fetcher);
    await expect(api.cancelDeletion(requestedDeletion.id)).rejects.toMatchObject({ code: 'network_error' });
    expect(fetcher).toHaveBeenCalledOnce();
    await expect(api.cancelDeletion(requestedDeletion.id)).resolves.toEqual(canceled);
    expect(fetcher.mock.calls.map(([path]) => path)).toEqual([
      `/api/v1/account/deletion-request/${requestedDeletion.id}/cancel`,
      `/api/v1/account/deletion-request/${requestedDeletion.id}/cancel`,
    ]);
    expect(fetcher.mock.calls[1][1]?.body).toBe(fetcher.mock.calls[0][1]?.body);
  });
});

describe('explicit account identity changes', () => {
  it('keeps disabled login accessible as a read-only state without sending mail or creating an identity', async () => {
    const fetcher = vi.fn<typeof fetch>();
    const identities = transition();
    const flow = createAccountFlow(createAccountApi(fetcher, identities), identities, createAccountLink());
    await expect(flow.requestLink({ ...config, enabled: false }, {
      email: account.email, policy_version: config.policy_version!, accept_policy: true,
    })).rejects.toMatchObject({ code: 'accounts_disabled' });
    expect(fetcher).not.toHaveBeenCalled();
    expect(identities.transition).not.toHaveBeenCalled();
  });

  it('erases the URL before retaining the token, never persists a secret, and waits for explicit completion', async () => {
    const token = randomBytes(32).toString('base64url');
    const page = browser(`https://example.org/auth/complete#token=${token}`);
    const setItem = vi.fn();
    vi.stubGlobal('localStorage', { setItem });
    vi.stubGlobal('sessionStorage', { setItem });
    const database = vi.spyOn(indexedDB, 'open');
    const log = vi.spyOn(console, 'log').mockImplementation(() => undefined);
    const link = createAccountLink(() => {
      expect(page.location.href).toBe('https://example.org/#/auth/complete');
      return Date.now();
    });
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json(account));
    const identities = transition();
    const flow = createAccountFlow(createAccountApi(fetcher, identities), identities, link);
    expect(link.capture(page.location, page.history)).toBe('ready');
    expect(page.history.replaceState).toHaveBeenCalledExactlyOnceWith(null, '', '/#/auth/complete');
    expect(fetcher).not.toHaveBeenCalled();
    expect(JSON.stringify(link)).not.toContain(token);
    await flow.complete();
    expect(identities.transition).toHaveBeenCalledOnce();
    expect(fetcher).toHaveBeenCalledWith('/api/v1/auth/complete', expect.objectContaining({
      body: JSON.stringify({ token }), headers: expect.objectContaining({ 'X-Requested-With': 'math-ege' }),
    }));
    expect(fetcher.mock.calls[0][1]?.headers).not.toHaveProperty('Idempotency-Key');
    expect(setItem).not.toHaveBeenCalled();
    expect(database).not.toHaveBeenCalled();
    expect(log).not.toHaveBeenCalled();
    expect(link.status()).toBe('empty');
  });

  it('coalesces completion and recovers a lost response by reading the refreshed account, without a second POST', async () => {
    const token = randomBytes(32).toString('base64url');
    const page = browser(`https://example.org/auth/complete#token=${token}`);
    const link = createAccountLink();
    link.capture(page.location, page.history);
    const fetcher = vi.fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError('connection closed'))
      .mockResolvedValueOnce(Response.json(account));
    const identities = transition();
    const flow = createAccountFlow(createAccountApi(fetcher, identities), identities, link);
    const first = flow.complete();
    expect(flow.complete()).toBe(first);
    await first;
    expect(fetcher.mock.calls.map(([path]) => path)).toEqual(['/api/v1/auth/complete', '/api/v1/account']);
    expect(identities.transition).toHaveBeenCalledOnce();
    expect(flow.getSnapshot()).toMatchObject({ completionRecovery: 'current', error: null });
    expect(link.status()).toBe('empty');
  });

  it('checks access read-only after an uncertain transition, even if complete is called again', async () => {
    const page = browser(`https://example.org/auth/complete#token=${randomBytes(32).toString('base64url')}`);
    const link = createAccountLink();
    link.capture(page.location, page.history);
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => Response.json(account));
    const identities = transition();
    const snapshot = vi.spyOn(identities, 'getSnapshot').mockReturnValue({ value: null, ready: true, changing: false, error: 'unavailable', epoch: 1 });
    const flow = createAccountFlow(createAccountApi(fetcher, identities), identities, link);
    await expect(flow.complete()).rejects.toMatchObject({ code: 'completion_unconfirmed' });
    expect(link.status()).toBe('ready');
    expect(flow.getSnapshot().completionRecovery).toBe('check');
    snapshot.mockRestore();
    await flow.complete();
    expect(identities.refresh).toHaveBeenCalledOnce();
    expect(fetcher.mock.calls.map(([path]) => path)).toEqual(['/api/v1/auth/complete', '/api/v1/account']);
    expect(link.status()).toBe('empty');
  });

  it('offers a new explicit confirmation only after read-only checks confirm there is no account session', async () => {
    const page = browser(`https://example.org/account#token=${randomBytes(32).toString('base64url')}`);
    const link = createAccountLink();
    link.capture(page.location, page.history);
    const fetcher = vi.fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError('request was not delivered'))
      .mockResolvedValue(Response.json({ error: { code: 'account_required' } }, { status: 401 }));
    const identities = transition(null);
    const flow = createAccountFlow(createAccountApi(fetcher, identities), identities, link);
    await expect(flow.complete()).rejects.toMatchObject({ code: 'completion_unconfirmed' });
    await expect(flow.complete()).rejects.toMatchObject({ code: 'login_not_confirmed' });
    expect(flow.getSnapshot().completionRecovery).toBe('none');
    expect(fetcher.mock.calls.filter(([path]) => path === '/api/v1/auth/complete')).toHaveLength(1);
    expect(link.status()).toBe('ready');
    vi.spyOn(identities, 'getSnapshot').mockReturnValue(transition().getSnapshot());
    fetcher.mockResolvedValueOnce(Response.json(account));
    await flow.complete();
    const posts = fetcher.mock.calls.filter(([path]) => path === '/api/v1/auth/complete');
    expect(posts).toHaveLength(2);
    expect(posts[1][1]?.body).toBe(posts[0][1]?.body);
  });

  it('does not resolve a received completion response against a different authenticated account', async () => {
    const page = browser(`https://example.org/account#token=${randomBytes(32).toString('base64url')}`);
    const link = createAccountLink();
    link.capture(page.location, page.history);
    const other = { ...account, id: 'account-two', root_guest_id: 'owner-two', owner_ids: ['owner-two'] };
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(Response.json(account)).mockImplementation(async () => Response.json(other));
    const identities = transition(other);
    const flow = createAccountFlow(createAccountApi(fetcher, identities), identities, link);
    await expect(flow.complete()).rejects.toMatchObject({ code: 'completion_unconfirmed' });
    await expect(flow.complete()).rejects.toMatchObject({ code: 'completion_unconfirmed' });
    expect(fetcher.mock.calls.filter(([path]) => path === '/api/v1/auth/complete')).toHaveLength(1);
    expect(link.status()).toBe('ready');
  });

  it('treats a used link as a final rejection even when an account is already signed in', async () => {
    const page = browser(`https://example.org/account#token=${randomBytes(32).toString('base64url')}`);
    const link = createAccountLink();
    link.capture(page.location, page.history);
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ error: { code: 'invalid_link' } }, { status: 400 }));
    const identities = transition();
    const flow = createAccountFlow(createAccountApi(fetcher, identities), identities, link);
    await expect(flow.complete()).rejects.toMatchObject({ code: 'invalid_link' });
    expect(fetcher).toHaveBeenCalledOnce();
    expect(link.status()).toBe('invalid');
  });

  it('keeps read-only recovery when identity becomes uncertain during the account check', async () => {
    const page = browser(`https://example.org/account#token=${randomBytes(32).toString('base64url')}`);
    const link = createAccountLink();
    link.capture(page.location, page.history);
    const fetcher = vi.fn<typeof fetch>().mockRejectedValue(new TypeError('offline'));
    const identities = transition(null);
    const snapshot = vi.spyOn(identities, 'getSnapshot');
    const flow = createAccountFlow(createAccountApi(fetcher, identities), identities, link);
    await expect(flow.complete()).rejects.toMatchObject({ code: 'completion_unconfirmed' });
    let resolve!: (response: Response) => void;
    fetcher.mockImplementationOnce(() => new Promise<Response>((done) => { resolve = done; }));
    const checking = flow.complete();
    await vi.waitFor(() => expect(resolve).toBeDefined());
    snapshot.mockReturnValue({ value: null, ready: true, changing: false, error: 'unavailable', epoch: 1 });
    resolve(Response.json({ error: { code: 'account_required' } }, { status: 401 }));
    await expect(checking).rejects.toMatchObject({ code: 'completion_unconfirmed' });
    expect(flow.getSnapshot().completionRecovery).toBe('check');
    expect(fetcher.mock.calls.filter(([path]) => path === '/api/v1/auth/complete')).toHaveLength(1);
  });

  it('uses the transition seam for logout and this device, but not for a different device', async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => Response.json({ ok: true }));
    const identities = transition();
    const flow = createAccountFlow(createAccountApi(fetcher, identities), identities, createAccountLink());
    await flow.revokeSession({ ...session, current: false });
    expect(identities.transition).not.toHaveBeenCalled();
    await flow.revokeSession(session);
    await flow.logout();
    expect(identities.transition).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls.map(([path]) => path)).toEqual([
      '/api/v1/account/sessions/session-one/revoke', '/api/v1/account/sessions/session-one/revoke', '/api/v1/auth/logout',
    ]);
  });

  it('keeps a sanitized completion error available when the transition remounts the UI', async () => {
    const token = randomBytes(32).toString('base64url');
    const page = browser(`https://example.org/auth/complete#token=${token}`);
    const link = createAccountLink();
    link.capture(page.location, page.history);
    const identities = transition();
    const flow = createAccountFlow(createAccountApi(vi.fn<typeof fetch>().mockRejectedValue(new Error(token)), identities), identities, link);
    const listener = vi.fn();
    const unmount = flow.subscribe(listener);
    const pending = flow.complete();
    unmount();
    await expect(pending).rejects.toMatchObject({ code: 'completion_unconfirmed' });
    expect(flow.getSnapshot()).toMatchObject({ action: null, lastAction: 'complete', completionRecovery: 'check', error: accountErrorText(new AccountError(0, 'completion_unconfirmed')) });
    expect(JSON.stringify(flow.getSnapshot())).not.toContain(token);
    expect(link.status()).toBe('ready');
  });

  it('retains an MFA setup across a rejected confirmation, bound to its account and only in memory', async () => {
    const secret = [...randomBytes(32)].map((value) => 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'[value % 32]).join('');
    const uri = `otpauth://totp/Exam?secret=${secret}`;
    const expiresAt = new Date(Date.now() + 600_000).toISOString();
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({ secret, provisioning_uri: uri, expires_at: expiresAt }))
      .mockResolvedValueOnce(Response.json({ error: { code: 'invalid_mfa' } }, { status: 400 }))
      .mockResolvedValueOnce(Response.json({ enabled: true, verified_until: new Date(Date.now() + 900_000).toISOString() }));
    const persist = vi.fn();
    vi.stubGlobal('sessionStorage', { setItem: persist });
    vi.stubGlobal('localStorage', { setItem: persist });
    const identities = transition();
    const flow = createAccountFlow(createAccountApi(fetcher, identities), identities, createAccountLink());
    await flow.enrollMfa(account.id);
    expect(flow.enrollment(account.id)).toEqual({ provisioning_uri: uri, expires_at: expiresAt });
    expect(flow.enrollment('another-account')).toBeNull();
    expect(JSON.stringify(flow.getSnapshot())).not.toContain(secret);
    await expect(flow.confirmMfa('000123')).rejects.toMatchObject({ code: 'mfa_invalid' });
    expect(flow.enrollment(account.id)?.provisioning_uri).toBe(uri);
    await flow.confirmMfa('000124');
    expect(flow.enrollment(account.id)).toBeNull();
    expect(identities.transition).toHaveBeenCalledTimes(2);
    expect(persist).not.toHaveBeenCalled();
  });

  it('forgets an in-memory enrollment after current-session revocation', async () => {
    const secret = [...randomBytes(32)].map((value) => 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'[value % 32]).join('');
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({ provisioning_uri: `otpauth://totp/Exam?secret=${secret}`, expires_at: new Date(Date.now() + 600_000).toISOString() }))
      .mockResolvedValueOnce(Response.json({ ok: true }));
    const identities = transition();
    const flow = createAccountFlow(createAccountApi(fetcher, identities), identities, createAccountLink());
    await flow.enrollMfa(account.id);
    await flow.revokeSession(session);
    expect(flow.enrollment(account.id) === null).toBe(true);
  });

  it('validates a code before quiescing identity queues or sending a request', async () => {
    const fetcher = vi.fn<typeof fetch>();
    const identities = transition();
    const flow = createAccountFlow(createAccountApi(fetcher, identities), identities, createAccountLink());
    await expect(flow.verifyMfa('1e2345')).rejects.toMatchObject({ code: 'invalid_code' });
    await expect(flow.confirmMfa('12345')).rejects.toMatchObject({ code: 'invalid_code' });
    expect(identities.transition).not.toHaveBeenCalled();
    expect(fetcher).not.toHaveBeenCalled();
  });
});

describe('fragment rejection and bounded secret lifetime', () => {
  it.each(['?token=anything', '#token=one&token=two', '#token=short', '#wrong=value', ''])('rejects %s and erases the completion URL', async (suffix) => {
    const page = browser(`https://example.org/auth/complete${suffix}`);
    const link = createAccountLink();
    expect(link.capture(page.location, page.history)).toBe('invalid');
    expect(page.location.href).toBe('https://example.org/#/auth/complete');
    const action = vi.fn();
    await expect(link.submit(action)).rejects.toMatchObject({ code: 'invalid_link' });
    expect(action).not.toHaveBeenCalled();
  });

  it('does not accept a token when URL erasure fails', async () => {
    const page = browser(`https://example.org/auth/complete#token=${randomBytes(32).toString('base64url')}`);
    page.history.replaceState.mockImplementation(() => { throw new Error('blocked'); });
    const link = createAccountLink();
    expect(link.capture(page.location, page.history)).toBe('invalid');
    await expect(link.submit(vi.fn())).rejects.toMatchObject({ code: 'invalid_link' });
  });

  it('preserves a captured intent through repeated bootstrap calls and drops it after fifteen minutes', async () => {
    let now = 0;
    const page = browser(`https://example.org/account#token=${randomBytes(32).toString('base64url')}`);
    const link = createAccountLink(() => now);
    expect(link.capture(page.location, page.history)).toBe('ready');
    expect(link.capture(page.location, page.history)).toBe('ready');
    now = 15 * 60 * 1000;
    const action = vi.fn();
    await expect(link.submit(action)).rejects.toMatchObject({ code: 'invalid_link' });
    expect(action).not.toHaveBeenCalled();
  });

  it('discards a permanently rejected browser-bound token instead of retrying it', async () => {
    const page = browser(`https://example.org/auth/complete#token=${randomBytes(32).toString('base64url')}`);
    const link = createAccountLink();
    link.capture(page.location, page.history);
    await expect(link.submit(async () => { throw new AccountError(400, 'invalid_link'); })).rejects.toMatchObject({ code: 'invalid_link' });
    expect(link.status()).toBe('invalid');
  });
});

describe('account input and staff gates', () => {
  it.each(['000123', '123456', ' 123456 '])('accepts a complete pasted TOTP code %s', (code) => {
    expect(normalizeMfaCode(code)).toBe(code.trim());
  });
  it.each(['12345', '1234567', '12 3456', '1e2345', '-12345', '１２３４５６', '١٢٣٤٥٦', 'abcdef', ''])('rejects malformed TOTP %s', (code) => {
    expect(() => normalizeMfaCode(code)).toThrow(AccountError);
  });
  it('normalizes only supported email syntax', () => {
    expect(normalizeEmail(' Student+Practice@Example.org ')).toBe('student+practice@example.org');
    for (const email of ['a..b@example.org', 'a@localhost', 'имя@example.org', 'a@-example.org', 'a@x..org']) {
      expect(() => normalizeEmail(email)).toThrow(AccountError);
    }
  });
  it('allows the editor affordance only for server staff with enabled, unexpired MFA', () => {
    const now = Date.parse('2026-11-05T10:00:00Z');
    const staff = { ...account, role: 'methodist' as const, mfa_enabled: true, mfa_verified_until: '2026-11-05T10:15:00Z' };
    expect(hasRecentMfa(staff, now)).toBe(true);
    expect(hasRecentMfa({ ...staff, role: 'student' }, now)).toBe(false);
    expect(hasRecentMfa({ ...staff, mfa_enabled: false }, now)).toBe(false);
    expect(hasRecentMfa(staff, now + 900_000)).toBe(false);
    expect(hasRecentMfa({ ...staff, mfa_verified_until: 'invalid' }, now)).toBe(false);
  });
  it('does not render executable policy URLs', () => {
    expect(safePolicyUrl('https://example.org/privacy')).toBe('https://example.org/privacy');
    expect(safePolicyUrl('javascript:alert(1)')).toBeNull();
    expect(safePolicyUrl('https://user:password@example.org/privacy')).toBeNull();
  });
});
