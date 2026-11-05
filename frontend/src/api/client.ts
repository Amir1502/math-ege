import type { Attempt, AttemptBody, DraftBody, Hint, LearningSession, Lesson, Profile, Progress, Solution, StartBody } from './types';
import { parseHistoryExport } from './history-export';
import { identity } from '../storage/identity';

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly field: string | null = null,
  ) {
    super(message);
    this.name = 'ApiError';
  }

  get retryable() {
    return this.status === 0 || this.status >= 500 || this.status === 429;
  }
}

export async function request<T>(path: string, method = 'GET', body?: unknown, key?: string, owner = identity.current()): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  const privateRequest = !/^\/(?:auth(?:\/|$)|identity$|guest$|profile$|lessons(?:\/|$)|curriculum$)/.test(path);
  if (privateRequest && owner) {
    if (identity.getSnapshot().changing || identity.current() !== owner) {
      throw new ApiError(409, 'identity_changed', 'Доступ изменился. Откройте занятие заново; локальный ввод сохранён.');
    }
    headers['X-Learning-Owner'] = owner;
  }
  if (method !== 'GET') {
    headers['Content-Type'] = 'application/json';
    headers['X-Requested-With'] = 'math-ege';
  }
  if (key) headers['Idempotency-Key'] = key;

  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      method,
      headers,
      credentials: 'same-origin',
      cache: 'no-store',
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    throw new ApiError(0, 'network_error', 'Нет связи с сервером. Проверьте соединение и повторите отправку.');
  }

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = (payload as { error?: { code?: string; message?: string; field?: string | null } } | null)?.error;
    throw new ApiError(
      response.status,
      error?.code ?? 'http_error',
      error?.message ?? 'Сервер не выполнил запрос. Повторите позже.',
      error?.field ?? null,
    );
  }
  if (payload === null) throw new ApiError(502, 'invalid_response', 'Сервер вернул неполный ответ. Повторите запрос.');
  return payload as T;
}

function createApi(owner?: string | null) {
  const call = <T>(path: string, method = 'GET', body?: unknown, key?: string) => request<T>(path, method, body, key, owner);
  return {
  profile: () => call<Profile>('/profile'),
  lesson: (slot: number) => call<Lesson>(`/lessons/${slot}`),
  progress: () => call<Progress>('/progress'),
  export: async () => {
    const snapshot = identity.getSnapshot();
    const exportOwner = owner === undefined ? identity.current() : owner;
    const changed = () => {
      const current = identity.getSnapshot();
      return current.changing || current.error !== null || current.epoch !== snapshot.epoch || identity.current() !== exportOwner;
    };
    const identityChanged = () => new ApiError(409, 'identity_changed', 'Доступ изменился. Откройте историю заново.');
    if (changed()) throw identityChanged();
    let current = true;
    const unsubscribe = identity.subscribe(() => { if (changed()) current = false; });
    try {
      const payload = await call<unknown>('/export');
      if (!current || changed()) throw identityChanged();
      try { return parseHistoryExport(payload); }
      catch { throw new ApiError(502, 'invalid_response', 'Не удалось прочитать полную историю. Повторите загрузку.'); }
    } finally { unsubscribe(); }
  },
  guest: () => call<{ id: string }>('/guest', 'POST', {}),
  start: (body: StartBody, key: string) => call<LearningSession>('/sessions', 'POST', body, key),
  session: (id: string) => call<LearningSession>(`/sessions/${encodeURIComponent(id)}`),
  draft: (id: string, body: DraftBody) => call<{ draft_revision: number }>(`/sessions/${encodeURIComponent(id)}/draft`, 'PUT', body),
  attempt: (id: string, body: AttemptBody, key: string) => call<Attempt>(`/sessions/${encodeURIComponent(id)}/attempts`, 'POST', body, key),
  hint: (id: string, taskId: string, level: 1 | 2 | 3) => call<Hint>(`/sessions/${encodeURIComponent(id)}/hints`, 'POST', { task_id: taskId, level }),
  solution: (id: string, taskId: string) => call<Solution>(`/sessions/${encodeURIComponent(id)}/solution`, 'POST', { task_id: taskId }),
  finish: (id: string, key: string) => call<LearningSession>(`/sessions/${encodeURIComponent(id)}/finish`, 'POST', {}, key),
  extend: (id: string, key: string) => call<LearningSession>(`/sessions/${encodeURIComponent(id)}/extend`, 'POST', {}, key),
  };
}

export const api = createApi();
export const boundApi = (owner: string | null) => createApi(owner);

export type LearningApi = typeof api;

export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return 'Гостевой доступ не найден. Возможно, cookie удалены. Локальный черновик не удалён.';
    if (error.status === 404) return 'Материал или занятие недоступны в этом браузере.';
    if (error.status === 503) return error.message;
    if (error.code === 'bank_exhausted') return 'Новые задачи для этих номеров закончились. Выберите другие номера: встречавшиеся экземпляры не выдаются 30 дней.';
    return error.message;
  }
  return 'Не удалось сохранить данные. Проверьте доступ к хранилищу браузера и повторите.';
}
