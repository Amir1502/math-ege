import { AccountError, responseError } from './errors';
import type { Account, AccountApi, AccountIdentityAccess, AccountRequestAccess, AccessSession, AuthConfig, DeletionCancellation, DeletionRequest, MfaEnrollment, MfaStatus } from './types';
import { captureAccountAccess, guardAccountRequest } from './access';
import { deletionInstant } from './deletion-time';
import { normalizeEmail, normalizeMfaCode, safePolicyUrl } from './validation';
import { parseHistoryExport } from '../api/history-export';
import { identity } from '../storage/identity';

export const emailResponseMessage = 'Если адрес доступен для входа, письмо со ссылкой отправлено.';

function invalidResponse(): never { throw new AccountError(502, 'invalid_response'); }
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return invalidResponse();
  return value as Record<string, unknown>;
}
function text(value: unknown): string {
  if (typeof value !== 'string' || value.length === 0) return invalidResponse();
  return value;
}
function bool(value: unknown): boolean {
  if (typeof value !== 'boolean') return invalidResponse();
  return value;
}
function date(value: unknown): string {
  const result = text(value);
  if (!Number.isFinite(Date.parse(result))) return invalidResponse();
  return result;
}
function nullableDate(value: unknown): string | null { return value === null ? null : date(value); }
function list(value: unknown): unknown[] { return Array.isArray(value) ? value : invalidResponse(); }

function configView(payload: unknown): AuthConfig {
  const value = object(payload);
  const enabled = bool(value.enabled);
  if (value.link_ttl_seconds !== 900) return invalidResponse();
  const policy = value.policy_url === null ? null : safePolicyUrl(value.policy_url);
  const version = value.policy_version === null ? null : text(value.policy_version);
  if (enabled && (!policy || !version)) return invalidResponse();
  return {
    enabled, policy_version: version, policy_url: policy, link_ttl_seconds: value.link_ttl_seconds,
  };
}

function accountView(payload: unknown): Account {
  const value = object(payload);
  if (!['student', 'methodist', 'admin'].includes(String(value.role))
    || ![10, 20, 30].includes(value.daily_minutes as number)) return invalidResponse();
  return {
    id: text(value.id), email: text(value.email), email_verified: bool(value.email_verified),
    role: value.role as Account['role'], root_guest_id: text(value.root_guest_id),
    owner_ids: list(value.owner_ids).map(text), created_at: date(value.created_at),
    policy_version: text(value.policy_version), consented_at: date(value.consented_at),
    daily_minutes: value.daily_minutes as Account['daily_minutes'],
    mfa_enabled: bool(value.mfa_enabled), mfa_verified_until: nullableDate(value.mfa_verified_until),
  };
}

function sessionView(payload: unknown): AccessSession {
  const value = object(payload);
  return {
    id: text(value.id), created_at: date(value.created_at), last_seen_at: date(value.last_seen_at),
    expires_at: date(value.expires_at), current: bool(value.current),
    mfa_verified_until: nullableDate(value.mfa_verified_until),
  };
}

const deletionId = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

function deletionDate(value: unknown): string {
  const result = date(value);
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(result)) return invalidResponse();
  const [year, month, day] = result.slice(0, 10).split('-').map(Number);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > days[month - 1]
    || Number(result.slice(11, 13)) > 23 || Number(result.slice(14, 16)) > 59 || Number(result.slice(17, 19)) > 59) return invalidResponse();
  return result;
}

function deletionPeriod(value: Record<string, unknown>) {
  const requested = deletionDate(value.requested_at);
  const deadline = deletionDate(value.deadline_at);
  const interval = deletionInstant(deadline) - deletionInstant(requested);
  if (interval < 0n || interval > 30n * 24n * 60n * 60n * 1_000_000n) return invalidResponse();
  return { requested_at: requested, deadline_at: deadline };
}

function deletionView(payload: unknown): DeletionRequest | null {
  if (payload === null) return null;
  const value = object(payload);
  if (value.status !== 'requested' || typeof value.id !== 'string' || !deletionId.test(value.id)) return invalidResponse();
  return { id: value.id, status: value.status, ...deletionPeriod(value) };
}

function cancellationView(payload: unknown, id: string): DeletionCancellation {
  const value = object(payload);
  const fields = ['id', 'status', 'requested_at', 'deadline_at', 'canceled_at'];
  if (Object.keys(value).length !== fields.length || fields.some((key) => !Object.hasOwn(value, key))
    || value.id !== id || value.status !== 'canceled') return invalidResponse();
  const period = deletionPeriod(value);
  const canceled = deletionDate(value.canceled_at);
  if (deletionInstant(canceled) < deletionInstant(period.requested_at)) return invalidResponse();
  return { id, status: 'canceled', ...period, canceled_at: canceled };
}

function enrollmentView(payload: unknown): MfaEnrollment {
  const value = object(payload);
  const uri = text(value.provisioning_uri);
  try {
    const parsed = new URL(uri);
    if (uri.length > 2048 || parsed.protocol !== 'otpauth:' || parsed.hostname !== 'totp'
      || parsed.username || parsed.password || !/^[A-Z2-7]{16,128}$/.test(parsed.searchParams.get('secret') ?? '')) return invalidResponse();
  } catch { return invalidResponse(); }
  // Drop the redundant raw secret; only the server-provided, copyable URI reaches the enrollment view.
  return { provisioning_uri: uri, expires_at: date(value.expires_at) };
}

function mfaView(payload: unknown): MfaStatus {
  const value = object(payload);
  if (value.enabled !== true) return invalidResponse();
  return { enabled: true, verified_until: date(value.verified_until) };
}

export function createAccountApi(
  fetcher: typeof fetch = (...args) => fetch(...args),
  access: AccountIdentityAccess = identity,
): AccountApi {
  async function request<T>(path: string, parse: (payload: unknown, guard: ReturnType<typeof guardAccountRequest> | null) => T, options: {
    method?: string;
    body?: unknown;
    public?: boolean;
    bootstrap?: boolean;
    transition?: AccountRequestAccess;
  } = {}): Promise<T> {
    const guard = options.public ? null : guardAccountRequest(access, options);
    const { method = 'GET', body } = options;
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (guard?.owner) headers['X-Learning-Owner'] = guard.owner;
    if (method !== 'GET') {
      headers['Content-Type'] = 'application/json';
      headers['X-Requested-With'] = 'math-ege';
    }
    try {
      guard?.check();
      let response: Response;
      try {
        const timeout = AbortSignal.timeout(15_000);
        response = await fetcher(`/api/v1${path}`, {
          method, headers, credentials: 'same-origin', cache: 'no-store', redirect: 'error',
          signal: guard ? AbortSignal.any([guard.signal, timeout]) : timeout,
          body: body === undefined ? undefined : JSON.stringify(body),
        });
      } catch { guard?.check(); throw new AccountError(0, 'network_error'); }
      guard?.check();
      const payload: unknown = await response.json().catch(() => null);
      guard?.check();
      if (!response.ok) {
        const code = (payload as { error?: { code?: unknown } } | null)?.error?.code;
        throw responseError(response.status, code);
      }
      if (payload === null) return invalidResponse();
      const result = parse(payload, guard);
      guard?.check();
      return result;
    } finally { guard?.close(); }
  }
  function success(path: string, transition?: AccountRequestAccess): Promise<void> {
    return request(path, (payload) => { if (object(payload).ok !== true) return invalidResponse(); }, { method: 'POST', body: {}, transition });
  }
  function scopedAccount(payload: unknown, guard: ReturnType<typeof guardAccountRequest> | null): Account {
    const account = accountView(payload);
    if (!guard?.owner || guard.kind !== 'account' || account.root_guest_id !== guard.owner) throw new AccountError(409, 'conflict');
    return account;
  }

  return {
    captureAccess: () => captureAccountAccess(access),
    config: () => request('/auth/config', configView, { public: true }),
    current: async () => {
      try { return await request('/account', scopedAccount, { bootstrap: true }); }
      catch (error) {
        if (error instanceof AccountError && error.status === 401) return null;
        throw error;
      }
    },
    requestLink: async (body) => {
      if (!body.accept_policy || !/^[A-Za-z0-9._-]{1,64}$/.test(body.policy_version)) throw new AccountError(422, 'consent_required');
      await request('/auth/request-link', (payload) => {
        if (typeof object(payload).message !== 'string') return invalidResponse();
      }, { public: true, method: 'POST', body: {
        email: normalizeEmail(body.email), policy_version: body.policy_version, accept_policy: true,
      } });
      // Successful requests deliberately reveal neither account existence nor mail delivery outcome.
    },
    complete: async (body) => {
      if (!/^[A-Za-z0-9_-]{43}$/.test(body.token)) throw new AccountError(400, 'invalid_link');
      return request('/auth/complete', accountView, { public: true, method: 'POST', body: { token: body.token } });
    },
    logout: (transition) => success('/auth/logout', transition),
    revokeSession: (id, transition) => success(`/account/sessions/${encodeURIComponent(id)}/revoke`, transition),
    updateSettings: (body) => request('/account', scopedAccount, { method: 'PATCH', body: { daily_minutes: body.daily_minutes } }),
    sessions: () => request('/account/sessions', (payload) => list(object(payload).sessions).map(sessionView)),
    deletionStatus: () => request('/account/deletion-request', (payload) => deletionView(object(payload).request)),
    requestDeletion: async (confirm) => {
      if (!confirm) throw new AccountError(422, 'confirmation_required');
      return request('/account/deletion-request', (payload) => deletionView(object(payload).request) ?? invalidResponse(), { method: 'POST', body: { confirm: true } });
    },
    cancelDeletion: async (id) => {
      if (!deletionId.test(id)) throw new AccountError(422, 'invalid_deletion_request');
      return request(`/account/deletion-request/${encodeURIComponent(id)}/cancel`, (payload) => cancellationView(payload, id), { method: 'POST', body: {} });
    },
    enrollMfa: () => request('/auth/mfa/enroll', enrollmentView, { method: 'POST', body: {} }),
    confirmMfa: async (code, transition) => request('/auth/mfa/confirm', mfaView, { method: 'POST', body: { code: normalizeMfaCode(code) }, transition }),
    verifyMfa: async (code, transition) => request('/auth/mfa/verify', mfaView, { method: 'POST', body: { code: normalizeMfaCode(code) }, transition }),
    exportHistory: () => request('/export', (payload) => {
      try { return parseHistoryExport(payload); }
      catch { return invalidResponse(); }
    }),
  };
}

export const accountApi = createAccountApi();
