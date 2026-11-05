import { api as learningApi, ApiError } from '../api/client';
import type { PublicTask } from '../api/types';
import type { AssessmentApi, AssessmentResult, AssessmentView, ResultRow } from './types';

type WireRow = Omit<ResultRow, 'raw_answer' | 'normalized_answer' | 'expected_answer'> & {
  raw: string; normalized: string | null; expected: string;
};
type WireResult = Omit<AssessmentResult, 'rows'> & { rows: WireRow[] };
type WireView = Omit<AssessmentView, 'server_result' | 'local_result'> & {
  server_result: WireResult | null; local_result: WireResult | null;
};

function invalidResponse(): never {
  throw new ApiError(502, 'invalid_response', 'Сервер вернул неполный вариант. Начало не подтверждено. Повторите загрузку.');
}

export function completeConditions(tasks: PublicTask[]): boolean {
  return Array.isArray(tasks) && tasks.length === 13
    && new Set(tasks.map((task) => task?.id)).size === 13
    && new Set(tasks.map((task) => task?.slot)).size === 13
    && tasks.every((task) => task && typeof task.id === 'string' && task.id.length > 0
      && Number.isInteger(task.slot) && task.slot >= 1 && task.slot <= 13
      && typeof task.title === 'string' && typeof task.topic === 'string'
      && typeof task.statement === 'string' && task.statement.trim().length > 0
      && (task.formula === null || typeof task.formula === 'string')
      && (task.table === null || (Array.isArray(task.table?.headers) && Array.isArray(task.table?.rows)
        && task.table.headers.every((item) => typeof item === 'string')
        && task.table.rows.every((row) => Array.isArray(row) && row.every((cell) => typeof cell === 'string')))));
}

function result(value: WireResult | null): AssessmentResult | null {
  if (value === null) return null;
  if (!value || value.total !== 13 || !Number.isInteger(value.score) || value.score < 0 || value.score > 13
    || !Array.isArray(value.rows) || value.rows.length !== 13) return invalidResponse();
  return {
    score: value.score, total: 13, connection_lost: value.connection_lost === true,
    recommendation: typeof value.recommendation === 'string' ? value.recommendation : '',
    rows: value.rows.map((row) => {
      if (!row || typeof row.task_id !== 'string' || typeof row.raw !== 'string'
        || typeof row.expected !== 'string' || (row.normalized !== null && typeof row.normalized !== 'string')
        || !Array.isArray(row.solution) || !row.solution.every((step) => typeof step === 'string')
        || ['correct', 'skipped', 'format_error', 'independent', 'assisted'].some((key) => typeof row[key as keyof WireRow] !== 'boolean')) return invalidResponse();
      return {
        task_id: row.task_id, raw_answer: row.raw, normalized_answer: row.normalized,
        expected_answer: row.expected, correct: row.correct, skipped: row.skipped,
        format_error: row.format_error, format_message: typeof row.format_message === 'string' ? row.format_message : null,
        independent: row.independent, assisted: row.assisted, solution: row.solution,
      };
    }),
  };
}

function view(payload: unknown): AssessmentView {
  const value = payload as WireView | null;
  if (!value || typeof value.id !== 'string' || !['diagnostic', 'exam'].includes(value.mode)
    || !['prepared', 'active', 'awaiting_snapshot', 'completed'].includes(value.status)
    || !completeConditions(value.tasks) || !Number.isFinite(Date.parse(value.server_now))
    || (value.deadline_at !== null && !Number.isFinite(Date.parse(value.deadline_at)))
    || !Number.isInteger(value.writer_generation) || value.writer_generation < 1
    || !Number.isInteger(value.draft_revision) || value.draft_revision < 0
    || !Number.isInteger(value.current_index) || value.current_index < 0 || value.current_index > 12
    || typeof value.can_write !== 'boolean' || !value.drafts || typeof value.drafts !== 'object'
    || (value.status !== 'completed' && (value.server_result !== null || value.local_result !== null))) return invalidResponse();
  for (const draft of Object.values(value.drafts)) {
    if (!draft || typeof draft.answer !== 'string' || draft.answer.length > 64
      || !Number.isInteger(draft.active_seconds) || draft.active_seconds < 0) return invalidResponse();
  }
  return {
    id: value.id, mode: value.mode, status: value.status, server_now: value.server_now,
    started_at: value.started_at, deadline_at: value.deadline_at, duration_minutes: value.duration_minutes,
    writer_generation: value.writer_generation, can_write: value.can_write,
    draft_revision: value.draft_revision, current_index: value.current_index,
    tasks: value.tasks, drafts: value.drafts,
    server_result: result(value.server_result), local_result: result(value.local_result),
    result_notice: typeof value.result_notice === 'string' ? value.result_notice : '',
  };
}

export function createAssessmentApi(ownerId: string, fetcher: typeof fetch = (...args) => fetch(...args)): AssessmentApi {
  async function request(path: string, method = 'GET', body?: unknown, key?: string, deviceId?: string): Promise<unknown> {
    const headers: Record<string, string> = { Accept: 'application/json', 'X-Learning-Owner': ownerId };
    if (method !== 'GET') {
      headers['Content-Type'] = 'application/json';
      headers['X-Requested-With'] = 'math-ege';
    }
    if (key) headers['Idempotency-Key'] = key;
    if (deviceId) headers['X-Assessment-Device'] = deviceId;
    let response: Response;
    try {
      response = await fetcher(`/api/v1/assessments${path}`, {
        method, headers, credentials: 'same-origin', cache: 'no-store',
        signal: AbortSignal.timeout(15_000), body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new ApiError(0, 'network_error', 'Нет ответа сервера. Черновик сохранён на устройстве. Повторите отправку.');
    }
    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const error = (payload as { error?: { code?: string; message?: string; field?: string } } | null)?.error;
      throw new ApiError(response.status, error?.code ?? 'http_error', error?.message ?? 'Сервер не выполнил запрос. Повторите позже.', error?.field ?? null);
    }
    return payload;
  }
  const path = (id: string) => `/${encodeURIComponent(id)}`;
  return {
    guest: learningApi.guest,
    prepare: async (body, key) => view(await request('', 'POST', body, key)),
    get: async (id, device) => view(await request(path(id), 'GET', undefined, undefined, device)),
    activate: async (id, body, key) => view(await request(`${path(id)}/activate`, 'POST', body, key)),
    draft: async (id, body) => {
      const payload = await request(`${path(id)}/draft`, 'PUT', body) as { draft_revision?: number } | null;
      if (!payload || !Number.isInteger(payload.draft_revision) || payload.draft_revision! < 0) return invalidResponse();
      return { draft_revision: payload.draft_revision! };
    },
    takeover: async (id, body, key) => view(await request(`${path(id)}/takeover`, 'POST', body, key)),
    finish: async (id, body, key) => view(await request(`${path(id)}/finish`, 'POST', body, key)),
  };
}
