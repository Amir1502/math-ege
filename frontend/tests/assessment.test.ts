import { afterEach, describe, expect, it, vi } from 'vitest';
import { createAssessmentApi } from '../src/assessments/api';
import { ApiError } from '../src/api/client';
import { AssessmentController } from '../src/assessments/controller';
import { AssessmentRepository } from '../src/assessments/storage';
import { AssessmentPreparation } from '../src/assessments/prepare';
import type { AssessmentApi, AssessmentView } from '../src/assessments/types';
import type { AssessmentRecord, AssessmentStorage } from '../src/assessments/model';
import { deferred } from './fixtures';

const device = '04b713ae-730c-46e6-a936-c7271966bb75';
const owner = 'guest-one';

function assessment(overrides: Partial<AssessmentView> = {}): AssessmentView {
  return {
    id: 'assessment-one', mode: 'diagnostic', status: 'active', server_now: '2026-11-05T12:00:00Z',
    started_at: '2026-11-05T12:00:00Z', deadline_at: null, duration_minutes: 65,
    writer_generation: 1, can_write: true, draft_revision: 0, current_index: 0,
    tasks: Array.from({ length: 13 }, (_, index) => ({
      id: `task-${index + 1}`, revision: '1', slot: index + 1, topic: 'Тестовый номер',
      title: 'Тестовое условие', statement: 'Только тестовое условие.', formula: null, table: null,
      skill_ids: ['skill'], family_id: 'family', estimated_seconds: 60, review_status: 'demo', hint_count: 3,
    })),
    drafts: {}, server_result: null, local_result: null, result_notice: '', ...overrides,
  };
}

function fakeApi(view = assessment()): AssessmentApi {
  let revision = view.draft_revision;
  return {
    guest: vi.fn(async () => ({ id: owner })),
    get: vi.fn(async () => structuredClone(view)),
    prepare: vi.fn(async () => assessment({ status: 'prepared', started_at: null })),
    activate: vi.fn(async () => assessment()),
    draft: vi.fn(async () => ({ draft_revision: ++revision })),
    takeover: vi.fn(async () => assessment({ writer_generation: 2 })),
    finish: vi.fn(async () => assessment({ status: 'completed', can_write: false })),
  };
}

function memoryStorage(): AssessmentStorage {
  let saved: AssessmentRecord | undefined;
  let journal: AssessmentRecord | undefined;
  return {
    load: async () => structuredClone(journal ?? saved),
    save: async (record) => { saved = structuredClone(record); },
    journal: (record) => { journal = structuredClone(record); },
  };
}

function browserStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() { return values.size; },
    key: (index) => [...values.keys()][index] ?? null,
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => { values.set(key, value); },
    removeItem: (key) => { values.delete(key); },
    clear: () => { values.clear(); },
  };
}

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('assessment public HTTP boundary', () => {
  it('sends the device header and uses cookie credentials without caching GETs', async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ error: { code: 'not_found', message: 'Недоступно' } }), { status: 404 }));
    const api = createAssessmentApi(owner, fetcher);
    await expect(api.get('assessment one', '04b713ae-730c-46e6-a936-c7271966bb75')).rejects.toMatchObject({ status: 404, code: 'not_found' });
    expect(fetcher).toHaveBeenCalledWith('/api/v1/assessments/assessment%20one', expect.objectContaining({
      method: 'GET', credentials: 'same-origin', cache: 'no-store',
      headers: expect.objectContaining({ 'X-Assessment-Device': '04b713ae-730c-46e6-a936-c7271966bb75', 'X-Learning-Owner': owner }),
    }));
  });

  it('sends the exact final body/key under the captured owner and adapts released wire results', async () => {
    const key = crypto.randomUUID();
    const body = { device_id: device, writer_generation: 1, connection_lost: false,
      answers: { 'task-1': { answer: '1/2', active_seconds: 3 } },
    };
    const released = { score: 0, total: 13, connection_lost: false, recommendation: 'Разберите ошибки.',
      rows: assessment().tasks.map((task, index) => ({ task_id: task.id, raw: index === 0 ? '1/2' : '', normalized: null,
        expected: '2', correct: false, skipped: index > 0, format_error: index === 0, format_message: null,
        independent: false, assisted: false, solution: ['Авторский разбор.'],
      })),
    };
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ ...assessment({ status: 'completed' }), server_result: released })));
    const reply = await createAssessmentApi(owner, fetcher).finish('assessment one', body, key);
    expect(fetcher).toHaveBeenCalledExactlyOnceWith('/api/v1/assessments/assessment%20one/finish', expect.objectContaining({
      method: 'POST', credentials: 'same-origin', cache: 'no-store', body: JSON.stringify(body),
      headers: expect.objectContaining({ 'X-Learning-Owner': owner, 'X-Requested-With': 'math-ege',
        'Content-Type': 'application/json', 'Idempotency-Key': key }),
    }));
    expect(reply.server_result?.rows[0]).toMatchObject({ raw_answer: '1/2', normalized_answer: null, expected_answer: '2', format_error: true });
    expect(reply.server_result?.rows[0]).not.toHaveProperty('raw');
  });

  it('rejects partial conditions and unreleased result payloads', async () => {
    const partial = { ...assessment({ status: 'prepared' }), tasks: assessment().tasks.slice(0, 12) };
    const leaked = { ...assessment(), server_result: { score: 0, total: 13, rows: [] } };
    for (const payload of [partial, leaked]) {
      const fetcher = vi.fn(async () => new Response(JSON.stringify(payload)));
      await expect(createAssessmentApi(owner, fetcher).get('assessment-one', device)).rejects.toMatchObject({ code: 'invalid_response' });
    }
  });
});

describe('assessment public controller', () => {
  it('never acknowledges newer input with a stale draft response and flushes the queued value', async () => {
    vi.useFakeTimers();
    const api = fakeApi();
    const first = deferred<{ draft_revision: number }>();
    api.draft = vi.fn().mockImplementationOnce(() => first.promise).mockResolvedValue({ draft_revision: 2 });
    const controller = new AssessmentController('assessment-one', owner, device, api, memoryStorage());
    await controller.load();
    controller.edit('12');
    const flushing = controller.flush();
    await vi.advanceTimersByTimeAsync(0);
    controller.edit('12,50');
    first.resolve({ draft_revision: 1 });
    await flushing;
    expect(api.draft).toHaveBeenNthCalledWith(1, 'assessment-one', expect.objectContaining({ expected_revision: 0, answers: expect.objectContaining({ 'task-1': { answer: '12', active_seconds: 0 } }) }));
    expect(api.draft).toHaveBeenNthCalledWith(2, 'assessment-one', expect.objectContaining({ expected_revision: 1, answers: expect.objectContaining({ 'task-1': { answer: '12,50', active_seconds: 0 } }) }));
    expect(controller.getSnapshot().record?.drafts['task-1'].answer).toBe('12,50');
    expect(controller.getSnapshot().dirty).toBe(false);
    controller.dispose();
  });

  it('freezes the exact offline final before HTTP and restores it read-only after a reload', async () => {
    vi.useFakeTimers();
    const api = fakeApi();
    const storage = memoryStorage();
    const first = new AssessmentController('assessment-one', owner, device, api, storage);
    await first.load();
    first.edit('−12,50');
    first.setOnline(false);
    first.goTo(12);
    await first.finish();
    const frozen = structuredClone(first.getSnapshot().record?.frozen);
    expect(frozen?.body.answers['task-1'].answer).toBe('−12,50');
    expect(frozen?.body.answers['task-13'].answer).toBe('');
    expect(frozen?.body.connection_lost).toBe(true);
    expect(api.finish).not.toHaveBeenCalled();
    first.dispose();

    const resumed = new AssessmentController('assessment-one', owner, device, api, storage);
    resumed.setOnline(false);
    await resumed.load();
    expect(resumed.getSnapshot().record?.current_index).toBe(12);
    expect(resumed.getSnapshot().readOnly).toBe(true);
    resumed.goTo(0);
    resumed.edit('different answer');
    expect(resumed.getSnapshot().record?.drafts['task-1'].answer).toBe('−12,50');
    resumed.setOnline(true);
    await resumed.retry();
    expect(api.finish).toHaveBeenCalledExactlyOnceWith('assessment-one', frozen?.body, frozen?.key);
    expect(resumed.getSnapshot().record?.view.status).toBe('completed');
    resumed.dispose();
  });

  it('retains a CAS-conflicted answer across reload and requires a deliberate resolution before writing', async () => {
    vi.useFakeTimers();
    const api = fakeApi();
    const storage = memoryStorage();
    api.draft = vi.fn(async () => { throw new ApiError(409, 'assessment_draft_conflict', 'Черновик изменён'); });
    const first = new AssessmentController('assessment-one', owner, device, api, storage);
    await first.load();
    first.edit('3,50');
    await first.flush();
    expect(first.getSnapshot().record?.conflict).toBe('revision');
    expect(first.getSnapshot().readOnly).toBe(true);
    first.edit('8');
    expect(first.getSnapshot().record?.drafts['task-1'].answer).toBe('3,50');
    first.dispose();

    api.get = vi.fn(async () => assessment({ draft_revision: 2, drafts: { 'task-1': { answer: '99', active_seconds: 7 } } }));
    api.draft = vi.fn(async () => ({ draft_revision: 3 }));
    const resumed = new AssessmentController('assessment-one', owner, device, api, storage);
    await resumed.load();
    await resumed.retry();
    expect(api.draft).not.toHaveBeenCalled();
    expect(resumed.getSnapshot().record?.drafts['task-1'].answer).toBe('3,50');
    await resumed.resolveConflict('local');
    expect(api.draft).toHaveBeenCalledExactlyOnceWith('assessment-one', expect.objectContaining({ expected_revision: 2, answers: expect.objectContaining({ 'task-1': { answer: '3,50', active_seconds: 0 } }) }));
    expect(resumed.getSnapshot().readOnly).toBe(false);
    resumed.dispose();
  });

  it('anchors the deadline to server time across hidden time, offline reload, and a backward wall-clock change', async () => {
    vi.useFakeTimers();
    let wall = Date.parse('2026-11-05T20:00:00Z');
    let monotonic = 0;
    const clock = { wallNow: () => wall, monotonicNow: () => monotonic };
    const api = fakeApi(assessment({ mode: 'exam', duration_minutes: 15, deadline_at: '2026-11-05T12:15:00Z' }));
    const storage = memoryStorage();
    const first = new AssessmentController('assessment-one', owner, device, api, storage, clock);
    await first.load();
    expect(first.getSnapshot().remainingSeconds).toBe(900);
    first.setVisible(true);
    wall += 60_000; monotonic += 60_000;
    first.tick();
    first.setVisible(false);
    wall += 300_000; monotonic += 300_000;
    first.tick();
    expect(first.getSnapshot().remainingSeconds).toBe(540);
    expect(first.getSnapshot().record?.drafts['task-1'].active_seconds).toBe(60);
    first.setOnline(false);
    await first.persist();
    first.dispose();

    monotonic = 0;
    const resumed = new AssessmentController('assessment-one', owner, device, api, storage, clock);
    resumed.setOnline(false);
    await resumed.load();
    expect(resumed.getSnapshot().remainingSeconds).toBe(540);
    wall -= 60_000;
    monotonic += 541_000;
    resumed.tick();
    await resumed.persist();
    expect(resumed.getSnapshot().remainingSeconds).toBe(0);
    expect(resumed.getSnapshot().readOnly).toBe(true);
    expect(resumed.getSnapshot().record?.frozen?.body.answers['task-1'].active_seconds).toBe(60);
    expect(resumed.getSnapshot().record?.view.server_result).toBeNull();
    expect(api.finish).not.toHaveBeenCalled();
    resumed.dispose();
  });

  it('preserves the old owner partition and ignores late acknowledgements after the identity barrier', async () => {
    vi.useFakeTimers();
    const api = fakeApi();
    const reply = deferred<{ draft_revision: number }>();
    const storage = memoryStorage();
    const controller = new AssessmentController('assessment-one', owner, device, api, storage);
    await controller.load();
    api.draft = vi.fn(() => reply.promise);
    controller.edit('7');
    const flushing = controller.flush();
    await vi.advanceTimersByTimeAsync(0);
    await controller.suspend();
    reply.resolve({ draft_revision: 5 });
    await flushing;
    controller.edit('new identity input');
    await controller.refresh();
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(controller.getSnapshot().readOnly).toBe(true);
    expect(controller.getSnapshot().record?.view.draft_revision).toBe(0);
    expect((await storage.load(owner, 'assessment-one', device))?.drafts['task-1'].answer).toBe('7');
    controller.dispose();
  });

  it('keeps a second writer read-only until a confirmed generation takeover', async () => {
    vi.useFakeTimers();
    const api = fakeApi(assessment({ can_write: false, writer_generation: 4 }));
    api.takeover = vi.fn(async () => assessment({ writer_generation: 5, drafts: { 'task-1': { answer: 'server draft', active_seconds: 2 } } }));
    const controller = new AssessmentController('assessment-one', owner, device, api, memoryStorage());
    await controller.load();
    controller.edit('unconfirmed write');
    await controller.flush();
    expect(api.draft).not.toHaveBeenCalled();
    expect(controller.getSnapshot().readOnly).toBe(true);
    await controller.takeover();
    expect(api.takeover).toHaveBeenCalledExactlyOnceWith('assessment-one', { device_id: device, writer_generation: 4 }, expect.any(String));
    expect(controller.getSnapshot().readOnly).toBe(false);
    expect(controller.getSnapshot().record?.drafts['task-1'].answer).toBe('server draft');
    controller.edit('5');
    await controller.flush();
    expect(api.draft).toHaveBeenCalledWith('assessment-one', expect.objectContaining({ writer_generation: 5 }));
    controller.dispose();
  });

  it('persists all conditions and the activation key before starting, and recovers from failed storage', async () => {
    vi.useFakeTimers();
    const api = fakeApi(assessment({ status: 'prepared', started_at: null }));
    const storage = memoryStorage();
    const save = storage.save;
    const controller = new AssessmentController('assessment-one', owner, device, api, storage);
    await controller.load();
    storage.save = vi.fn(async () => { throw new Error('Quota'); });
    await controller.activate();
    expect(api.activate).not.toHaveBeenCalled();
    expect(controller.getSnapshot().storageError).toBeTruthy();
    const pending = structuredClone(controller.getSnapshot().record?.pending_activation);
    storage.save = save;
    api.activate = vi.fn(async (_id, body, key) => {
      const stored = await storage.load(owner, 'assessment-one', device);
      expect(stored?.view.tasks).toHaveLength(13);
      expect(stored?.pending_activation).toEqual({ key, body });
      return assessment();
    });
    await controller.activate();
    expect(api.activate).toHaveBeenCalledExactlyOnceWith('assessment-one', pending?.body, pending?.key);
    expect(controller.getSnapshot().record?.pending_activation).toBeNull();
    expect(controller.getSnapshot().record?.view.status).toBe('active');
    controller.dispose();
  });

  it('freezes and sends the last draft when the server has already reached awaiting_snapshot', async () => {
    vi.useFakeTimers();
    const api = fakeApi(assessment({ mode: 'exam', status: 'awaiting_snapshot', server_now: '2026-11-05T12:16:00Z', deadline_at: '2026-11-05T12:15:00Z', drafts: { 'task-1': { answer: '4,2', active_seconds: 80 } } }));
    const reply = deferred<AssessmentView>();
    api.finish = vi.fn(() => reply.promise);
    const controller = new AssessmentController('assessment-one', owner, device, api, memoryStorage());
    await controller.load();
    await vi.advanceTimersByTimeAsync(0);
    expect(controller.getSnapshot().record?.frozen?.body.answers['task-1'].answer).toBe('4,2');
    expect(controller.getSnapshot().record?.view.server_result).toBeNull();
    expect(controller.getSnapshot().readOnly).toBe(true);
    expect(api.finish).toHaveBeenCalledTimes(1);
    reply.resolve(assessment({ status: 'completed' }));
    await controller.finish();
    controller.dispose();
  });

  it.each(['assessment_draft_conflict', 'assessment_writer_conflict'])('holds a frozen finish when an in-flight draft reports %s', async (code) => {
    vi.useFakeTimers();
    const api = fakeApi();
    const reply = deferred<{ draft_revision: number }>();
    api.draft = vi.fn(() => reply.promise);
    const controller = new AssessmentController('assessment-one', owner, device, api, memoryStorage());
    await controller.load();
    controller.edit('8,5');
    const flushing = controller.flush();
    await vi.advanceTimersByTimeAsync(0);
    expect(api.draft).toHaveBeenCalledTimes(1);
    const finishing = controller.finish();
    await vi.advanceTimersByTimeAsync(0);
    reply.reject(new ApiError(409, code, 'Конфликт записи'));
    await Promise.all([flushing, finishing]);
    expect(api.finish).not.toHaveBeenCalled();
    expect(controller.getSnapshot().record?.frozen?.body.answers['task-1'].answer).toBe('8,5');
    expect(controller.getSnapshot().record?.conflict).toBe(code === 'assessment_draft_conflict' ? 'revision' : 'writer');
    expect(controller.getSnapshot().readOnly).toBe(true);
    controller.dispose();
  });

  it('reconciles a draft rejected at the server deadline and submits the last local snapshot', async () => {
    vi.useFakeTimers();
    const api = fakeApi();
    api.get = vi.fn().mockResolvedValueOnce(assessment()).mockResolvedValue(assessment({
      mode: 'exam', status: 'awaiting_snapshot', deadline_at: '2026-11-05T12:15:00Z', server_now: '2026-11-05T12:16:00Z',
    }));
    api.draft = vi.fn(async () => { throw new ApiError(409, 'assessment_not_active', 'Черновики закрыты'); });
    const controller = new AssessmentController('assessment-one', owner, device, api, memoryStorage());
    await controller.load();
    controller.edit('4,5');
    await controller.flush();
    await controller.finish();
    expect(api.get).toHaveBeenCalledTimes(2);
    expect(api.finish).toHaveBeenCalledExactlyOnceWith('assessment-one', expect.objectContaining({
      answers: expect.objectContaining({ 'task-1': { answer: '4,5', active_seconds: 0 } }),
    }), expect.any(String));
    expect(controller.getSnapshot().record?.view.status).toBe('completed');
    expect(controller.getSnapshot().record?.conflict).toBeNull();
    controller.dispose();
  });

  it('loads the released server result after an immutable snapshot conflict', async () => {
    vi.useFakeTimers();
    const api = fakeApi();
    api.get = vi.fn().mockResolvedValueOnce(assessment()).mockResolvedValue(assessment({ status: 'completed', can_write: false }));
    api.finish = vi.fn(async () => { throw new ApiError(409, 'assessment_snapshot_conflict', 'Итог уже зафиксирован'); });
    const controller = new AssessmentController('assessment-one', owner, device, api, memoryStorage());
    await controller.load();
    controller.edit('6');
    await controller.finish();
    expect(api.get).toHaveBeenCalledTimes(2);
    expect(api.finish).toHaveBeenCalledTimes(1);
    expect(controller.getSnapshot().record?.view.status).toBe('completed');
    expect(controller.getSnapshot().record?.conflict).toBeNull();
    expect(controller.getSnapshot().record?.frozen?.body.answers['task-1'].answer).toBe('6');
    controller.dispose();
  });

  it('continues a saved activation whose response was lost until after the deadline', async () => {
    vi.useFakeTimers();
    const api = fakeApi();
    api.get = vi.fn().mockResolvedValueOnce(assessment({ status: 'prepared', started_at: null })).mockResolvedValue(assessment({
      mode: 'exam', status: 'awaiting_snapshot', deadline_at: '2026-11-05T12:15:00Z', server_now: '2026-11-05T12:16:00Z',
    }));
    api.activate = vi.fn(async () => { throw new ApiError(409, 'assessment_closed', 'Приём закрыт'); });
    const controller = new AssessmentController('assessment-one', owner, device, api, memoryStorage());
    await controller.load();
    await controller.activate();
    await vi.advanceTimersByTimeAsync(0);
    expect(api.get).toHaveBeenCalledTimes(2);
    expect(api.finish).toHaveBeenCalledTimes(1);
    expect(controller.getSnapshot().record?.view.status).toBe('completed');
    controller.dispose();
  });

  it('retries a confirmed takeover with its saved request after a network failure', async () => {
    vi.useFakeTimers();
    const api = fakeApi(assessment({ can_write: false, writer_generation: 4 }));
    api.takeover = vi.fn().mockRejectedValueOnce(new ApiError(0, 'network_error', 'Нет сети'))
      .mockResolvedValue(assessment({ writer_generation: 5 }));
    const controller = new AssessmentController('assessment-one', owner, device, api, memoryStorage());
    await controller.load();
    await controller.takeover();
    const pending = structuredClone(controller.getSnapshot().record?.pending_takeover);
    expect(controller.getSnapshot().readOnly).toBe(true);
    await controller.retry();
    expect(api.takeover).toHaveBeenCalledTimes(2);
    expect(api.takeover).toHaveBeenLastCalledWith('assessment-one', pending?.body, pending?.key);
    expect(controller.getSnapshot().record?.pending_takeover).toBeNull();
    expect(controller.getSnapshot().readOnly).toBe(false);
    controller.dispose();
  });

  it('ignores older GET responses after an acknowledged draft and after final release', async () => {
    vi.useFakeTimers();
    const api = fakeApi();
    const controller = new AssessmentController('assessment-one', owner, device, api, memoryStorage());
    await controller.load();
    const oldDraft = deferred<AssessmentView>();
    api.get = vi.fn(() => oldDraft.promise);
    const refreshingDraft = controller.refresh();
    controller.edit('12,5');
    await controller.flush();
    oldDraft.resolve(assessment());
    await refreshingDraft;
    expect(controller.getSnapshot().record?.drafts['task-1'].answer).toBe('12,5');
    expect(controller.getSnapshot().record?.view.draft_revision).toBe(1);
    expect(controller.getSnapshot().record?.conflict).toBeNull();

    const oldActive = deferred<AssessmentView>();
    api.get = vi.fn(() => oldActive.promise);
    const refreshingActive = controller.refresh();
    api.finish = vi.fn(async () => assessment({ status: 'completed', can_write: false, draft_revision: 1 }));
    await controller.finish();
    oldActive.resolve(assessment({ draft_revision: 1 }));
    await refreshingActive;
    expect(controller.getSnapshot().record?.view.status).toBe('completed');
    expect(controller.getSnapshot().readOnly).toBe(true);
    controller.dispose();
  });

  it('sends a durable frozen snapshot when the document reloads already online', async () => {
    vi.useFakeTimers();
    const api = fakeApi();
    const storage = memoryStorage();
    const first = new AssessmentController('assessment-one', owner, device, api, storage);
    await first.load();
    first.setOnline(false);
    first.edit('2,75');
    await first.finish();
    const frozen = structuredClone(first.getSnapshot().record?.frozen);
    first.dispose();
    const resumed = new AssessmentController('assessment-one', owner, device, api, storage);
    await resumed.load();
    await vi.advanceTimersByTimeAsync(0);
    expect(api.finish).toHaveBeenCalledExactlyOnceWith('assessment-one', frozen?.body, frozen?.key);
    expect(resumed.getSnapshot().record?.view.status).toBe('completed');
    resumed.dispose();
  });

  it.each(['draft', 'activate'] as const)('rechecks writer ownership after persisting a %s request', async (kind) => {
    vi.useFakeTimers();
    const status = kind === 'activate' ? 'prepared' : 'active';
    const api = fakeApi(assessment({ status }));
    const storage = memoryStorage();
    const controller = new AssessmentController('assessment-one', owner, device, api, storage);
    await controller.load();
    const saved = deferred<void>();
    storage.save = vi.fn().mockImplementationOnce(() => saved.promise).mockResolvedValue(undefined);
    if (kind === 'draft') controller.edit('7,25');
    const sending = kind === 'draft' ? controller.flush() : controller.activate();
    await vi.advanceTimersByTimeAsync(0);
    api.get = vi.fn(async () => assessment({ status, can_write: false, writer_generation: 2 }));
    const refreshing = controller.refresh();
    await vi.advanceTimersByTimeAsync(0);
    expect(controller.getSnapshot().readOnly).toBe(true);
    saved.resolve();
    await Promise.all([sending, refreshing]);
    expect(api[kind]).not.toHaveBeenCalled();
    expect(controller.getSnapshot().record?.conflict).toBe('writer');
    if (kind === 'draft') expect(controller.getSnapshot().record?.drafts['task-1'].answer).toBe('7,25');
    controller.dispose();
  });

  it('requires a fresh confirmation when a saved takeover generation has become obsolete', async () => {
    vi.useFakeTimers();
    const api = fakeApi(assessment({ can_write: false, writer_generation: 4 }));
    api.takeover = vi.fn().mockRejectedValueOnce(new ApiError(0, 'network_error', 'Нет сети'))
      .mockResolvedValue(assessment({ writer_generation: 7 }));
    const controller = new AssessmentController('assessment-one', owner, device, api, memoryStorage());
    await controller.load();
    await controller.takeover();
    const previous = structuredClone(controller.getSnapshot().record?.pending_takeover);
    api.get = vi.fn(async () => assessment({ can_write: false, writer_generation: 6 }));
    await controller.retry();
    expect(api.takeover).toHaveBeenCalledTimes(1);
    expect(controller.getSnapshot().record?.pending_takeover).toBeNull();
    expect(controller.getSnapshot().readOnly).toBe(true);
    await controller.takeover();
    expect(api.takeover).toHaveBeenLastCalledWith('assessment-one', { device_id: device, writer_generation: 6 }, expect.not.stringMatching(previous!.key));
    expect(controller.getSnapshot().readOnly).toBe(false);
    controller.dispose();
  });

  it('recognizes its own in-flight revision observed by a refresh while retaining newer input', async () => {
    vi.useFakeTimers();
    const api = fakeApi();
    const reply = deferred<{ draft_revision: number }>();
    api.draft = vi.fn().mockImplementationOnce(() => reply.promise).mockResolvedValue({ draft_revision: 2 });
    const controller = new AssessmentController('assessment-one', owner, device, api, memoryStorage());
    await controller.load();
    controller.edit('4');
    const flushing = controller.flush();
    await vi.advanceTimersByTimeAsync(0);
    controller.edit('4,25');
    api.get = vi.fn(async () => assessment({ draft_revision: 1, drafts: {
      ...Object.fromEntries(assessment().tasks.map((task) => [task.id, { answer: '', active_seconds: 0 }])),
      'task-1': { answer: '4', active_seconds: 0 },
    } }));
    await controller.refresh();
    expect(controller.getSnapshot().record?.conflict).toBeNull();
    expect(controller.getSnapshot().record?.drafts['task-1'].answer).toBe('4,25');
    reply.resolve({ draft_revision: 1 });
    await flushing;
    expect(api.draft).toHaveBeenCalledTimes(2);
    expect(api.draft).toHaveBeenLastCalledWith('assessment-one', expect.objectContaining({ expected_revision: 1,
      answers: expect.objectContaining({ 'task-1': { answer: '4,25', active_seconds: 0 } }),
    }));
    expect(controller.getSnapshot().dirty).toBe(false);
    controller.dispose();
  });

  it('restores access only after the same captured owner is confirmed by a successful refresh', async () => {
    vi.useFakeTimers();
    const api = fakeApi();
    api.draft = vi.fn().mockRejectedValueOnce(new ApiError(401, 'unauthorized', 'Нужен доступ')).mockResolvedValue({ draft_revision: 1 });
    const controller = new AssessmentController('assessment-one', owner, device, api, memoryStorage());
    await controller.load();
    controller.edit('9');
    await controller.flush();
    expect(controller.getSnapshot().record?.conflict).toBe('access');
    expect(controller.getSnapshot().readOnly).toBe(true);
    await controller.retry();
    expect(api.draft).toHaveBeenCalledTimes(2);
    expect(controller.getSnapshot().readOnly).toBe(false);
    expect(controller.getSnapshot().record?.drafts['task-1'].answer).toBe('9');
    controller.dispose();
  });
});

describe('durable assessment preparation', () => {
  it('publishes the saved settings and failure for a setup remounted after canonical guest creation', async () => {
    const repository = new AssessmentRepository(`assessment-test-${crypto.randomUUID()}`, browserStorage());
    const api = fakeApi();
    const reply = deferred<AssessmentView>();
    api.prepare = vi.fn(() => reply.promise);
    const preparation = new AssessmentPreparation(owner, device, api, repository);
    const preparing = preparation.prepare('exam', 90);
    const failed = expect(preparing).rejects.toMatchObject({ code: 'network_error' });
    expect(preparation.getSnapshot().busy).toBe(true);
    await vi.waitFor(() => expect(api.prepare).toHaveBeenCalledTimes(1));
    reply.reject(new ApiError(0, 'network_error', 'Нет ответа сервера'));
    await failed;
    expect(preparation.getSnapshot()).toMatchObject({ busy: false, error: { code: 'network_error' },
      pending: { body: { mode: 'exam', duration_minutes: 90, device_id: device } },
    });
    const restored = new AssessmentPreparation(owner, device, api, repository);
    await restored.restore();
    expect(restored.getSnapshot().pending).toEqual(preparation.getSnapshot().pending);
    await repository.close();
  });

  it('replays a lost prepare response with the original body/key and saves all 13 conditions before returning', async () => {
    const repository = new AssessmentRepository(`assessment-test-${crypto.randomUUID()}`, browserStorage());
    const api = fakeApi();
    api.prepare = vi.fn(async (body, key) => {
      expect(await repository.pendingCreate(owner, device)).toEqual({ body, key });
      throw new ApiError(0, 'network_error', 'Response lost');
    });
    const first = new AssessmentPreparation(owner, device, api, repository);
    await expect(first.prepare('exam', 65)).rejects.toMatchObject({ code: 'network_error' });
    const pending = await repository.pendingCreate(owner, device);
    const prepared = assessment({ status: 'prepared', mode: 'exam', started_at: null });
    api.prepare = vi.fn(async () => prepared);
    const resumed = new AssessmentPreparation(owner, device, api, repository);
    await expect(resumed.prepare('diagnostic', 90)).resolves.toBe('assessment-one');
    expect(api.prepare).toHaveBeenCalledExactlyOnceWith(pending?.body, pending?.key);
    expect((await repository.load(owner, 'assessment-one', device))?.view.tasks).toHaveLength(13);
    expect(await repository.load('another-owner', 'assessment-one', device)).toBeUndefined();
    expect(await repository.pendingCreate(owner, device)).toBeNull();
    expect(api.activate).not.toHaveBeenCalled();
    await repository.close();
  });
});
