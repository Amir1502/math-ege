import {
  decodeBase, decodeMeta, decodePreview, decodeRevision, decodeRevisions, decodeSample,
  EditorError, jsonObject,
} from './adapters';
import type { JsonObject, Kind, Status } from './types';

export type Mutation = Readonly<{ path: string; method: 'POST' | 'PUT'; body: string; key: string; actorId: string }>;
export type Filters = { kind: Kind; status?: Status | ''; q: string; offset: number };
const base = '/api/v1/editor';

async function request(path: string, options: {
  actorId?: string; method?: 'GET' | 'POST' | 'PUT'; body?: string; key?: string; signal?: AbortSignal;
} = {}): Promise<unknown> {
  const headers: Record<string, string> = { Accept: 'application/json', 'X-Requested-With': 'math-ege' };
  if (options.actorId) headers['X-Editor-Actor'] = options.actorId;
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (options.key) headers['Idempotency-Key'] = options.key;
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      method: options.method ?? 'GET', credentials: 'same-origin', cache: 'no-store', redirect: 'error',
      headers, body: options.body, signal: options.signal,
    });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    throw new EditorError('Ответ сервера не получен. Повторите тот же запрос после восстановления сети.', 'network', 0, null, true);
  }
  let data: unknown;
  try { data = await response.json(); }
  catch {
    throw new EditorError('Ответ сервера не удалось прочитать. Повторите тот же запрос.', 'invalid_response', response.status, null, true);
  }
  if (!response.ok) {
    const value = data && typeof data === 'object' && 'error' in data ? data.error : null;
    const detail = value && typeof value === 'object' ? value as Record<string, unknown> : {};
    throw new EditorError(
      typeof detail.message === 'string' ? detail.message : 'Сервер отклонил запрос. Обновите данные редактора.',
      typeof detail.code === 'string' ? detail.code : 'editor_error', response.status,
      typeof detail.field === 'string' ? detail.field : null, response.status >= 500,
    );
  }
  return data;
}

/** Snapshot the serialized body before the first send; uncertain retries reuse it verbatim. */
export function prepareMutation(actorId: string, path: string, method: Mutation['method'], value: unknown, maxBytes: number): Mutation {
  let body: string;
  try { body = JSON.stringify(jsonObject(value)); }
  catch { throw new EditorError('Нужен конечный JSON-объект без исполняемых значений.', 'invalid_request', 422, 'payload'); }
  if (new TextEncoder().encode(body).length > maxBytes) {
    throw new EditorError('Пакет превышает допустимый размер запроса. Уменьшите JSON.', 'request_too_large', 413, 'payload');
  }
  return Object.freeze({ actorId, path, method, body, key: crypto.randomUUID() });
}
export function sendMutation(mutation: Mutation): Promise<unknown> {
  return request(mutation.path, { actorId: mutation.actorId, method: mutation.method, body: mutation.body, key: mutation.key });
}

export function createEditorApi(actorId?: string) {
  const get = (path: string, signal?: AbortSignal) => request(path, { actorId, signal });
  return {
    meta: async (signal?: AbortSignal) => decodeMeta(await get('/meta', signal)),
    revisions: async (filters: Filters, signal?: AbortSignal) => {
      const query = new URLSearchParams({ kind: filters.kind, q: filters.q, offset: String(filters.offset), limit: '10' });
      if (filters.status) query.set('status', filters.status);
      return decodeRevisions(await get(`/revisions?${query}`, signal));
    },
    base: async (filters: Filters, signal?: AbortSignal) => decodeBase(await get(`/base?${new URLSearchParams({ kind: filters.kind, q: filters.q, offset: String(filters.offset) })}`, signal)),
    revision: async (id: string, signal?: AbortSignal) => decodeRevision(await get(`/revisions/${encodeURIComponent(id)}`, signal)),
    preview: async (kind: Kind, payload: JsonObject, signal?: AbortSignal) => decodePreview(await request('/preview', {
      actorId, method: 'POST', body: JSON.stringify({ kind, payload, change_note: 'Проверка предварительного просмотра.' }), signal,
    })),
    sample: async (id: string, seed: number, signal?: AbortSignal) => decodeSample(await get(`/revisions/${encodeURIComponent(id)}/sample?seed=${seed}`, signal)),
    export: async (ids: string[]) => {
      const query = new URLSearchParams(); ids.forEach(id => query.append('ids', id));
      return jsonObject(await get(`/export?${query}`));
    },
  };
}
export type EditorApi = ReturnType<typeof createEditorApi>;
