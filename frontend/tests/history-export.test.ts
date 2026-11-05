import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, boundApi } from '../src/api/client';
import { parseHistoryExport } from '../src/api/history-export';
import type {
  ExportAccount, ExportAssessment, ExportAssessmentResult, ExportLearningSession,
  ExportPublicTask, HistoryExport, ProfileSource,
} from '../src/api/types';
import { createAccountApi } from '../src/accounts/api';
import { identity } from '../src/storage/identity';
import { deferred, sessionFixture } from './fixtures';

const createdAt = '2026-11-05T12:00:00+00:00';
const releasedAt = '2026-11-05T12:16:00+00:00';

// HistoryExport.model_dump(mode='json') shapes, checked against real /export
// serialization: include default/null fields and ResultRow's raw/normalized/expected,
// not the adapted, partial assessment UI types or the old /account/export shape.
function profileFixture(): ProfileSource {
  return {
    id: 'profile-2026-approved', year: 2026, title: 'Профиль 2026', status: 'approved',
    revision: '2025-11-05.1', verified_at: '2025-11-05', verification_note: 'Историческая редакция.',
    source_urls: ['https://example.org/specification'],
    slots: Array.from({ length: 13 }, (_, index) => ({
      number: index + 1, id: `slot-${index + 1}`, title: `Номер ${index + 1}`, level: 'Б',
      summary: 'Краткий числовой ответ.', skills: [{ id: `skill-${index + 1}`, title: 'Вычисление' }],
      lesson_id: `lesson-${index + 1}`,
    })),
  };
}

function taskFixture(index: number): ExportPublicTask {
  const slot = (index - 1) % 13 + 1;
  return {
    id: `task-${index}`, revision: '1', slot, topic: 'Вычисление', title: 'Половина',
    statement: 'Найдите 2/4.', formula: '2/4', table: null, skill_ids: [`skill-${slot}`],
    family_id: `family-${slot}`, estimated_seconds: 60, review_status: 'demo', hint_count: 3,
    slot_id: null, figure: null, rounding: null,
  };
}

function practiceFixture(id = 'practice-one', length = 2, offset = 0): ExportLearningSession {
  const tasks = Array.from({ length }, (_, index) => taskFixture(offset + index + 1));
  const requestedLength = length > 10 ? 20 : 5;
  return {
    id, profile_id: 'profile-2026-approved', profile_revision: '2025-11-05.1', profile: profileFixture(),
    mode: 'practice', status: 'active', created_at: createdAt, completed_at: null, current_index: 1,
    requested_length: requestedLength, notice: null, draft_revision: 1, tasks,
    attempts: [{
      id: `${id}-attempt`, task_id: tasks[0].id, raw_answer: '0,5', normalized_answer: '0,5',
      correct: true, assisted: false, first_attempt: true, independent: true, skipped: false,
      active_seconds: 12, created_at: createdAt, expected_answer: '0,5', solution: ['2/4 = 0,5.'],
    }],
    drafts: { [tasks[1].id]: { answer: '', active_seconds: 3 } },
    help: { [tasks[1].id]: { hints: [{ level: 1, text: 'Сократите дробь.' }], solution: null } },
    summary: {
      total: tasks.length, answered: 1, independent_total: 1, independent_correct: 1,
      assisted: 0, corrections: 0, skipped: 0, active_seconds: 15,
    },
    options: {
      slots: [...new Set(tasks.map((task) => task.slot))], length: requestedLength, mode: 'practice',
      skill_ids: [], family_ids: [], difficulty: null, selection: 'balanced', repeat_task_id: null,
      until_stopped: false, target_minutes: null,
    },
  };
}

function resultFixture(source: 'server' | 'local', tasks: ExportPublicTask[]): ExportAssessmentResult {
  const local = source === 'local';
  return {
    source, reason: 'connection_lost', label: local ? 'Локальный учебный результат' : 'Учебная диагностика',
    score: local ? 1 : 0, total: 13, answered: local ? 1 : 0, skipped: local ? 12 : 13, format_errors: 0,
    independent_total: 0, independent_correct: 0, assisted_total: 0, active_seconds: local ? 8 : 0,
    elapsed_seconds: 960, snapshot_at: releasedAt, snapshot_hash: (local ? 'b' : 'a').repeat(64),
    connection_lost: true, checker_revision: 'fraction-v1-exam',
    rows: tasks.map((task, index) => {
      const answered = local && index === 0;
      return {
        id: `${source}-row-${index}`, task_id: task.id, task_revision: task.revision, slot: task.slot,
        slot_id: `slot-${task.slot}`, family_id: task.family_id, skill_ids: [...task.skill_ids],
        raw: answered ? '0,5' : '', normalized: answered ? '0,5' : null, expected: '0,5',
        correct: answered, skipped: !answered, format_error: false, format_message: null,
        independent: false, assisted: false, first_attempt: !local, active_seconds: answered ? 8 : 0,
        solution: ['2/4 = 0,5.'], first_draft: { answer: '', active_seconds: 0, recorded_at: releasedAt },
        first_answer: answered ? { answer: '0,5', active_seconds: 8, recorded_at: releasedAt } : null,
        label: answered ? 'Верно' : 'Пропущено',
      };
    }),
    weak_skill_ids: tasks.filter((_, index) => !local || index > 0).flatMap((task) => task.skill_ids),
    recommendation: 'Разберите ошибки и пропуски.',
  };
}

function assessmentFixture(status: ExportAssessment['status'] = 'completed'): ExportAssessment {
  const tasks = Array.from({ length: 13 }, (_, index) => ({ ...taskFixture(index + 1), hint_count: 0 }));
  return {
    id: `assessment-${status}`, mode: 'exam', status,
    profile_id: 'profile-2026-approved', profile_revision: '2025-11-05.1', profile: profileFixture(),
    created_at: createdAt, started_at: status === 'prepared' ? null : createdAt,
    deadline_at: status === 'prepared' ? null : '2026-11-05T12:15:00+00:00',
    released_at: status === 'completed' ? releasedAt : null, duration_minutes: 15, tasks,
    drafts: status === 'prepared' ? {} : Object.fromEntries(tasks.map((task) => [task.id, { answer: '', active_seconds: 0 }])),
    server_result: status === 'completed' ? resultFixture('server', tasks) : null,
    local_result: status === 'completed' ? resultFixture('local', tasks) : null,
    result_notice: status === 'completed' ? 'Снимки сохранены отдельно.' : 'Эталоны и решения пока закрыты.',
  };
}

function accountFixture(): ExportAccount {
  return {
    id: 'account-one', email: 'student@example.org', created_at: releasedAt, email_verified_at: releasedAt,
    role: 'student', daily_minutes: 20, consents: [{ policy_version: 'test-1', accepted_at: releasedAt }],
    deletion_request: {
      id: 'deletion-one', status: 'requested', requested_at: releasedAt, deadline_at: '2026-12-05T12:16:00+00:00',
    },
  };
}

function historyFixture(): HistoryExport {
  return JSON.parse(JSON.stringify({
    version: '1', exported_at: '2026-11-05T12:20:00+00:00', profile_id: 'profile-2027-draft',
    sessions: [practiceFixture()], assessments: [assessmentFixture()], account: accountFixture(),
    learning: {
      algorithm_version: 'learning-v1',
      annotations: [{
        id: 'annotation-one', session_id: 'practice-one', task_id: 'task-1', favourite: true,
        manual: false, not_understood: false, cause: 'format', created_at: createdAt, updated_at: releasedAt,
      }],
      reviews: [{
        skill_id: 'skill-1', family_id: 'family-1', slot_id: 'slot-1', due_at: '2026-11-06T12:00:00+00:00',
        interval_days: 1, closed: false, anchor_task_id: 'task-1', anchor_at: createdAt,
      }, {
        skill_id: 'skill-2', family_id: 'family-2', slot_id: 'slot-2', due_at: null,
        interval_days: 30, closed: true, anchor_task_id: 'task-2', anchor_at: createdAt,
      }],
      corrections: [{
        task_id: 'task-1', task_revision: '1', reason: 'Редакционная поправка.', created_at: releasedAt,
        attempt_ids: ['practice-one-attempt'], session_ids: ['practice-one'], assessment_ids: ['assessment-completed'],
      }],
    },
  })) as HistoryExport;
}

function confirmedIdentity(kind: 'guest' | 'account' = 'account') {
  const state: ReturnType<typeof identity.getSnapshot> = {
    value: { id: 'owner-one', kind, owner_ids: ['owner-one', 'claimed-guest'] },
    ready: true, changing: false, error: null, epoch: 1,
  };
  vi.spyOn(identity, 'current').mockImplementation(() => state.value?.id ?? null);
  vi.spyOn(identity, 'getSnapshot').mockImplementation(() => state);
  const listeners = new Set<() => void>();
  vi.spyOn(identity, 'subscribe').mockImplementation((listener) => {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  });
  return { state, publish: () => listeners.forEach((listener) => listener()), listeners };
}

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('complete export public DTO parser', () => {
  it('retains all seven root fields and every released result field without adapting the wire names', () => {
    const payload = historyFixture();
    const parsed = parseHistoryExport(payload);
    expect(parsed).toEqual(payload);
    expect(parsed).not.toBe(payload);
    expect(parsed.sessions[0].profile).not.toBe(payload.sessions[0].profile);
    expect(Object.keys(parsed)).toEqual(['version', 'exported_at', 'profile_id', 'sessions', 'assessments', 'learning', 'account']);
    const assessment = parsed.assessments[0];
    expect(assessment.server_result?.score).toBe(0);
    expect(assessment.local_result?.score).toBe(1);
    expect(assessment.local_result?.rows[0]).toMatchObject({
      raw: '0,5', normalized: '0,5', expected: '0,5',
      first_draft: { answer: '', active_seconds: 0, recorded_at: releasedAt },
      first_answer: { answer: '0,5', active_seconds: 8, recorded_at: releasedAt },
    });
    expect(assessment.local_result?.rows[0]).not.toHaveProperty('raw_answer');
    expect(assessment.local_result?.checker_revision).toBe('fraction-v1-exam');
    expect(assessment.server_result?.snapshot_hash).not.toBe(assessment.local_result?.snapshot_hash);
    expect(parsed.account).not.toHaveProperty('owner_ids');
    expect(parsed.account?.deletion_request?.status).toBe('requested');
  });

  it('keeps an old frozen source profile, independent of the current export profile', () => {
    const parsed = parseHistoryExport(historyFixture());
    expect(parsed.profile_id).toBe('profile-2027-draft');
    expect(parsed.sessions[0]).toMatchObject({
      profile_id: 'profile-2026-approved', profile_revision: '2025-11-05.1',
      profile: { id: 'profile-2026-approved', year: 2026, revision: '2025-11-05.1', status: 'approved' },
    });
    expect(parsed.sessions[0].profile).not.toHaveProperty('demo_mode');
    expect(parsed.sessions[0].profile).not.toHaveProperty('bank_size');
    expect(parsed.sessions[0].profile.slots[0]).not.toHaveProperty('available_tasks');
  });

  it('keeps older ordinary session responses compatible but requires historical fields for a complete export', () => {
    const legacy = sessionFixture();
    expect(legacy.profile).toBeUndefined();
    expect(legacy.profile_revision).toBeUndefined();
    for (const field of ['profile', 'profile_revision'] as const) {
      const payload = historyFixture();
      Reflect.deleteProperty(payload.sessions[0], field);
      expect(() => parseHistoryExport(payload)).toThrow(TypeError);
    }
  });

  it('preserves all sixty annotations across multiple histories, including false and cleared flags', () => {
    const payload = historyFixture();
    payload.sessions = [practiceFixture('practice-one', 20), practiceFixture('practice-two', 20, 20), practiceFixture('practice-three', 20, 40)];
    payload.learning.annotations = payload.sessions.flatMap((session) => session.tasks.map((task, index) => ({
      id: `${session.id}-annotation-${index}`, session_id: session.id, task_id: task.id,
      favourite: index % 2 === 0, manual: false, not_understood: index % 3 === 0,
      cause: index % 2 === 0 ? 'format' : null, created_at: createdAt, updated_at: releasedAt,
    })));
    const parsed = parseHistoryExport(payload);
    expect(parsed.learning.annotations).toHaveLength(60);
    expect(parsed.learning.annotations[59]).toEqual(payload.learning.annotations[59]);
    expect(parsed.learning.annotations).toEqual(payload.learning.annotations);
    expect(parsed.sessions).toHaveLength(3);
    expect(parsed.learning).not.toHaveProperty('pagination');
  });

  it('does not cap an extended practice history at its originally requested length', () => {
    const payload = historyFixture();
    payload.sessions = [practiceFixture('practice-one', 60)];
    payload.sessions[0].options!.until_stopped = true;
    expect(parseHistoryExport(payload).sessions[0].tasks).toHaveLength(60);
  });

  it('accepts null account data and empty histories without synthesizing a full Account', () => {
    const payload: HistoryExport = {
      version: '1', exported_at: releasedAt, profile_id: 'profile-current', sessions: [], assessments: [],
      learning: { algorithm_version: 'learning-v1', annotations: [], reviews: [], corrections: [] }, account: null,
    };
    expect(parseHistoryExport(payload)).toEqual(payload);
  });

  it('uses backend Unicode character limits, so valid historical draft text is not lost', () => {
    const payload = historyFixture();
    payload.sessions[0].drafts['task-2'].answer = '𝟙'.repeat(64);
    const taskId = '🧮'.repeat(128);
    payload.sessions[0].tasks[0].id = taskId;
    payload.sessions[0].attempts[0].task_id = taskId;
    expect(parseHistoryExport(payload).sessions[0].drafts['task-2'].answer).toBe('𝟙'.repeat(64));
  });

  it('preserves an untimed diagnostic assessment with a null deadline', () => {
    const payload = historyFixture();
    payload.assessments[0].mode = 'diagnostic';
    payload.assessments[0].deadline_at = null;
    expect(parseHistoryExport(payload).assessments[0]).toMatchObject({ mode: 'diagnostic', deadline_at: null });
  });

  it.each(['prepared', 'active', 'awaiting_snapshot'] as const)('accepts %s conditions and drafts, with both results still null', (status) => {
    const payload = historyFixture();
    payload.assessments = [assessmentFixture(status)];
    const parsed = parseHistoryExport(payload).assessments[0];
    expect(parsed.server_result).toBeNull();
    expect(parsed.local_result).toBeNull();
    expect(parsed.tasks).toHaveLength(13);
    expect(parsed.drafts).toEqual(payload.assessments[0].drafts);
  });

  it.each(['prepared', 'active', 'awaiting_snapshot'] as const)('rejects server or local results for %s assessments', (status) => {
    for (const source of ['server', 'local'] as const) {
      const payload = historyFixture();
      const assessment = assessmentFixture(status);
      assessment[source === 'server' ? 'server_result' : 'local_result'] = resultFixture(source, assessment.tasks);
      payload.assessments = [assessment];
      expect(() => parseHistoryExport(payload)).toThrow(TypeError);
    }
  });

  it('does not treat completed or future-dated labels as permission to expose unreleased results', () => {
    for (const released of [null, '2026-11-06T12:00:00+00:00']) {
      const payload = historyFixture();
      payload.assessments[0].released_at = released;
      expect(() => parseHistoryExport(payload)).toThrow(TypeError);
    }
  });

  it.each(['version', 'exported_at', 'profile_id', 'sessions', 'assessments', 'learning', 'account'])('requires the root %s field', (key) => {
    const payload = historyFixture();
    Reflect.deleteProperty(payload, key);
    expect(() => parseHistoryExport(payload)).toThrow(TypeError);
  });

  it.each([
    'token_digest', 'browser_state_digest', 'secret_ciphertext', 'last_timecode', 'writer_device_id',
    'writer_generation', 'mfa_verified_at', 'access_sessions', 'account_magic_links', 'tasks_snapshot',
    'private_snapshot', 'checker_rules', 'generator_params', 'arbitrary_extra',
  ])('rejects the forbidden or non-DTO field %s instead of silently stripping it', (key) => {
    for (const target of ['root', 'account', 'result'] as const) {
      const payload = historyFixture();
      const row = target === 'root' ? payload : target === 'account' ? payload.account! : payload.assessments[0].server_result!;
      Object.assign(row, { [key]: 'private-marker' });
      expect(() => parseHistoryExport(payload)).toThrow('Invalid complete history export.');
    }
  });

  it.each(['answer', 'hints', 'solution', 'expected', 'expected_answer', 'correct', 'source', 'grading'])('rejects %s on public task conditions', (key) => {
    const payload = historyFixture();
    Object.assign(payload.assessments[0].tasks[0], { [key]: 'private-marker' });
    expect(() => parseHistoryExport(payload)).toThrow(TypeError);
  });

  it('rejects current-profile runtime fields, ordinary account access fields and paginated dashboard data', () => {
    const mutations: ((payload: HistoryExport) => void)[] = [
      (payload) => { Object.assign(payload.sessions[0].profile, { demo_mode: true }); },
      (payload) => { Object.assign(payload.sessions[0].profile, { bank_size: 100 }); },
      (payload) => { Object.assign(payload.sessions[0].profile.slots[0], { available_tasks: 100 }); },
      (payload) => { Object.assign(payload.account!, { root_guest_id: 'owner-one' }); },
      (payload) => { Object.assign(payload.account!, { owner_ids: ['owner-one'] }); },
      (payload) => { Object.assign(payload.learning, { pagination: { offset: 0, limit: 20, totals: { annotations: 60 } } }); },
      (payload) => { Object.assign(payload.sessions[0].attempts[0], { checker_revision: 'internal-checker' }); },
    ];
    for (const mutate of mutations) {
      const payload = historyFixture();
      mutate(payload);
      expect(() => parseHistoryExport(payload)).toThrow(TypeError);
    }
  });

  it('rejects malformed scalar fields, result rows, task maps and inconsistent frozen revisions', () => {
    const mutations: ((payload: HistoryExport) => void)[] = [
      (payload) => { Object.assign(payload, { version: 1 }); },
      (payload) => { payload.exported_at = '2026-02-30T12:00:00+00:00'; },
      (payload) => { payload.exported_at = '2026-11-05T24:00:00+00:00'; },
      (payload) => { payload.sessions[0].profile_revision = 'different'; },
      (payload) => { Object.assign(payload.sessions[0], { profile: null }); },
      (payload) => { payload.sessions[0].tasks[0].id = 'x'.repeat(129); },
      (payload) => { payload.sessions[0].tasks[0].estimated_seconds = 0; },
      (payload) => { Object.assign(payload.sessions[0].tasks[0], { hint_count: '3' }); },
      (payload) => { payload.sessions[0].drafts['task-2'].answer = 'x'.repeat(65); },
      (payload) => { payload.sessions[0].drafts['task-2'].active_seconds = 86_401; },
      (payload) => { payload.sessions[0].drafts['unknown-task'] = { answer: '', active_seconds: 0 }; },
      (payload) => { Object.assign(payload.learning.annotations[0], { favourite: 'false' }); },
      (payload) => { Object.assign(payload.learning.annotations[0], { cause: 'unsupported' }); },
      (payload) => { payload.learning.reviews[0].interval_days = 1.5; },
      (payload) => { payload.learning.reviews[0].closed = true; },
      (payload) => { payload.sessions[0].summary.active_seconds = Number.MAX_SAFE_INTEGER + 1; },
      (payload) => { payload.assessments[0].server_result!.score = 14; },
      (payload) => { payload.assessments[0].server_result!.rows.pop(); },
      (payload) => { payload.assessments[0].server_result!.source = 'local'; },
      (payload) => { payload.assessments[0].server_result!.rows[0].task_revision = 'different'; },
      (payload) => { payload.assessments[0].server_result!.snapshot_hash = 'bad'; },
      (payload) => { payload.assessments[0].tasks[0].table = { headers: ['x', 'y'], rows: [['1']] }; },
      (payload) => { Object.assign(payload.account!, { daily_minutes: '20' }); },
      (payload) => { payload.account!.email = 'not-an-email'; },
      (payload) => { payload.account!.deletion_request!.deadline_at = '2026-12-06T12:16:00+00:00'; },
      (payload) => { Object.assign(payload.account!.deletion_request!, { status: 'completed' }); },
    ];
    for (const mutate of mutations) {
      const payload = historyFixture();
      mutate(payload);
      expect(() => parseHistoryExport(payload)).toThrow(TypeError);
    }
  });

  it('rejects invalid geometry and preserves correctly bounded serialized figures and rounding', () => {
    const payload = historyFixture();
    payload.sessions[0].tasks[0].figure = {
      description: 'Отрезок.', x_min: -1, x_max: 2, y_min: -1, y_max: 2, axes: true,
      lines: [{ points: [{ x: 0, y: 0 }, { x: 1, y: 1 }], dashed: false }],
      circles: [{ center: { x: 0, y: 0 }, radius: 1 }], labels: [{ x: 1, y: 1, text: 'A' }],
    };
    payload.sessions[0].tasks[0].rounding = { digits: 2, mode: 'half_up', instruction: 'До сотых.' };
    expect(parseHistoryExport(payload).sessions[0].tasks[0]).toEqual(payload.sessions[0].tasks[0]);
    for (const invalidCoordinate of [Infinity, NaN, 10_001]) {
      payload.sessions[0].tasks[0].figure.lines[0].points[0].x = invalidCoordinate;
      expect(() => parseHistoryExport(payload)).toThrow(TypeError);
    }
  });

  it('bounds the whole document and rejects oversized shapes rather than truncating histories', () => {
    const payload = historyFixture();
    Object.assign(payload.learning, { annotations: new Array(2_000_001).fill(null) });
    expect(() => parseHistoryExport(payload)).toThrow(TypeError);
    const oversizedText = historyFixture();
    oversizedText.sessions[0].tasks[0].statement = 'x'.repeat(1024 * 1024 + 1);
    expect(() => parseHistoryExport(oversizedText)).toThrow(TypeError);
    const oversizedDocument = historyFixture();
    oversizedDocument.sessions[0].attempts[0].solution = new Array(65).fill('x'.repeat(1024 * 1024));
    expect(() => parseHistoryExport(oversizedDocument)).toThrow(TypeError);
    const cyclic = historyFixture();
    Object.assign(cyclic, { nested: cyclic });
    expect(() => parseHistoryExport(cyclic)).toThrow(TypeError);
  });

  it('requires plain, dense JSON data without accessors or prototype keys', () => {
    for (const value of [null, [], new Date(), { ...historyFixture(), sessions: new Array(1) }, { ...historyFixture(), account: undefined }]) {
      expect(() => parseHistoryExport(value)).toThrow(TypeError);
    }
    const payload = historyFixture();
    const getter = vi.fn(() => 'private-marker');
    Object.defineProperty(payload.account!, 'secret_ciphertext', { enumerable: true, get: getter });
    expect(() => parseHistoryExport(payload)).toThrow(TypeError);
    expect(getter).not.toHaveBeenCalled();
    const prototypeKey = JSON.parse(JSON.stringify(historyFixture()).replace('"version":"1"', '"version":"1","__proto__":{}'));
    expect(() => parseHistoryExport(prototypeKey)).toThrow(TypeError);
  });
});

describe('complete export download adapters', () => {
  it('uses /export for account downloads and returns the complete minimal-account DTO', async () => {
    confirmedIdentity();
    const payload = historyFixture();
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json(payload));
    await expect(createAccountApi(fetcher).exportHistory()).resolves.toEqual(payload);
    expect(fetcher).toHaveBeenCalledExactlyOnceWith('/api/v1/export', expect.objectContaining({
      method: 'GET', credentials: 'same-origin', cache: 'no-store', redirect: 'error',
      headers: expect.objectContaining({ 'X-Learning-Owner': 'owner-one' }),
    }));
  });

  it('uses the same complete /export contract for a guest with no account', async () => {
    confirmedIdentity('guest');
    const payload = historyFixture();
    payload.account = null;
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json(payload));
    vi.stubGlobal('fetch', fetcher);
    await expect(boundApi('owner-one').export()).resolves.toEqual(payload);
    expect(fetcher).toHaveBeenCalledExactlyOnceWith('/api/v1/export', expect.objectContaining({
      method: 'GET', credentials: 'same-origin', cache: 'no-store',
      headers: expect.objectContaining({ 'X-Learning-Owner': 'owner-one' }),
    }));
  });

  it('rejects an incomplete practice-only export before it can be downloaded', async () => {
    confirmedIdentity('guest');
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json({
      version: '1', exported_at: createdAt, profile_id: 'profile-2027-draft', sessions: [],
    }));
    vi.stubGlobal('fetch', fetcher);
    await expect(boundApi('owner-one').export()).rejects.toMatchObject({
      name: 'ApiError', status: 502, code: 'invalid_response',
    });
  });

  it('keeps the existing bound learning-owner rejection before a request is sent', async () => {
    confirmedIdentity('guest');
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetcher);
    await expect(boundApi('stale-owner').export()).rejects.toBeInstanceOf(ApiError);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('accepts a null account on the account export route as part of the complete contract', async () => {
    confirmedIdentity();
    const payload = historyFixture();
    payload.account = null;
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json(payload));
    await expect(createAccountApi(fetcher).exportHistory()).resolves.toMatchObject({ account: null, version: '1' });
  });

  it.each(['learning', 'account'] as const)('rejects unsafe responses with sanitized errors in the %s adapter', async (adapter) => {
    confirmedIdentity();
    const payload = historyFixture();
    Object.assign(payload.account!, { secret_ciphertext: 'private-marker' });
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json(payload));
    vi.stubGlobal('fetch', fetcher);
    const error: unknown = await (adapter === 'account' ? createAccountApi(fetcher).exportHistory() : boundApi('owner-one').export()).catch((error: unknown) => error);
    expect(error).toMatchObject({ status: 502, code: 'invalid_response' });
    expect(String(error)).not.toContain('private-marker');
    expect(JSON.stringify(error)).not.toContain('private-marker');
  });

  it('blocks account exports while canonical access is unready, changing or uncertain', async () => {
    const { state } = confirmedIdentity();
    const fetcher = vi.fn<typeof fetch>();
    for (const change of [{ ready: false }, { ready: true, changing: true }, { changing: false, error: 'Uncertain access' }]) {
      Object.assign(state, change);
      await expect(createAccountApi(fetcher).exportHistory()).rejects.toMatchObject({ status: 409, code: 'conflict' });
    }
    expect(fetcher).not.toHaveBeenCalled();
  });

  it.each(['learning', 'account'] as const)('rejects a late %s export even after a same-owner identity transition finishes', async (adapter) => {
    const { state, publish, listeners } = confirmedIdentity();
    const response = deferred<Response>();
    const fetcher = vi.fn<typeof fetch>().mockReturnValue(response.promise);
    vi.stubGlobal('fetch', fetcher);
    const exporting = adapter === 'account' ? createAccountApi(fetcher).exportHistory() : boundApi('owner-one').export();
    expect(fetcher).toHaveBeenCalledOnce();
    state.changing = true;
    publish();
    state.changing = false;
    publish();
    response.resolve(Response.json(historyFixture()));
    await expect(exporting).rejects.toMatchObject({ status: 409 });
    expect(listeners.size).toBe(0);
  });
});
