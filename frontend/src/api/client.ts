import type { Attempt, AttemptBody, DraftBody, Hint, HistoryExport, LearningSession, Lesson, Profile, Progress, Solution, StartBody } from './types';

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

export async function request<T>(path: string, method = 'GET', body?: unknown, key?: string): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
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

export const api = {
  profile: () => request<Profile>('/profile'),
  lesson: (slot: number) => request<Lesson>(`/lessons/${slot}`),
  progress: () => request<Progress>('/progress'),
  export: () => request<HistoryExport>('/export'),
  guest: () => request<{ id: string }>('/guest', 'POST', {}),
  start: (body: StartBody, key: string) => request<LearningSession>('/sessions', 'POST', body, key),
  session: (id: string) => request<LearningSession>(`/sessions/${encodeURIComponent(id)}`),
  draft: (id: string, body: DraftBody) => request<{ draft_revision: number }>(`/sessions/${encodeURIComponent(id)}/draft`, 'PUT', body),
  attempt: (id: string, body: AttemptBody, key: string) => request<Attempt>(`/sessions/${encodeURIComponent(id)}/attempts`, 'POST', body, key),
  hint: (id: string, taskId: string, level: 1 | 2 | 3) => request<Hint>(`/sessions/${encodeURIComponent(id)}/hints`, 'POST', { task_id: taskId, level }),
  solution: (id: string, taskId: string) => request<Solution>(`/sessions/${encodeURIComponent(id)}/solution`, 'POST', { task_id: taskId }),
  finish: (id: string, key: string) => request<LearningSession>(`/sessions/${encodeURIComponent(id)}/finish`, 'POST', {}, key),
};

export type LearningApi = typeof api;

export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return 'Гостевой доступ не найден. Возможно, cookie удалены. Локальный черновик не удалён.';
    if (error.status === 404) return 'Материал или занятие недоступны в этом браузере.';
    if (error.status === 503) return 'Демонстрационный банк выключен на сервере. Для этого этапа нужен ALLOW_DEMO_CONTENT=true.';
    if (error.code === 'bank_exhausted') return 'Новые задачи для этих номеров закончились. Выберите другие номера: встречавшиеся экземпляры не выдаются 30 дней.';
    return error.message;
  }
  return 'Не удалось сохранить данные. Проверьте доступ к хранилищу браузера и повторите.';
}
