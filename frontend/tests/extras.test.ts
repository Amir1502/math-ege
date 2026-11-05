import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../src/api/client';
import { createLearningExtrasApi } from '../src/extras/api';
import { AnnotationWriter } from '../src/extras/annotations';
import { createLearningStore } from '../src/extras/store';
import { confirmedLearningOwner } from '../src/extras/identity';
import { IdentityManager } from '../src/storage/identity';
import {
  annotationValues, coverageSlots, currentTaskSlot, dueReviews, entryDescription, familyPracticePath,
  independentAccuracy, mixedPracticePath, mixedStartBody, originalProfileLabel, pageOffset, practiceHistoryPath,
} from '../src/extras/view-models';
import type { LearningDashboard, LearningExtrasApi, PracticeProgress, SavedAnnotation, TimePlan } from '../src/extras/types';
import { attemptFixture, deferred, sessionFixture } from './fixtures';

afterEach(() => vi.unstubAllGlobals());

function dashboardFixture(): LearningDashboard {
  return {
    algorithm_version: 'evidence-v1', notice: 'Статусы относятся к учебным данным.',
    independent_total: 24, independent_correct: 21, assisted_total: 2, corrections_total: 1, skipped_total: 1, excluded_total: 0,
    slots: [{
      slot_id: 'slot-probability', number: 4, title: 'Вероятность', status: 'Освоено',
      attempts: 24, correct: 21, covered_skills: 2, total_skills: 2,
      skills: [{ id: 'probability', title: 'Вероятность события', attempts: 24, correct: 21 }],
    }],
    reviews: [{
      skill_id: 'probability', family_id: 'family-basic', slot_id: 'slot-probability', slot: 4,
      due_at: '2026-11-06T12:00:00Z', interval_days: 3, overdue: false,
    }],
    weak_skills: [], favourites: [],
    journal: [{
      id: 'journal-one', session_id: 'test-session', task: sessionFixture().tasks[0], profile: null,
      attempt: attemptFixture(), cause: null, manual: false, not_understood: false,
    }],
    assessment_history: [], notifications: [], recommendation: 'Повторите навык по расписанию.',
    pagination: { offset: 0, limit: 50, totals: { journal: 1, reviews: 1, favourites: 0, assessment_history: 0 } },
  };
}

function progressFixture(): PracticeProgress {
  return {
    algorithm_version: 'learning-v1', notice: null, excluded_total: 0,
    independent_total: 2, independent_correct: 1, assisted_total: 3, corrections_total: 2, skipped_total: 4,
    active_session_id: 'active-practice', active_assessment_id: null,
    slots: [{ number: 4, status: 'Изучаю', attempts: 2, correct: 1, covered_skills: 1, total_skills: 2 }],
    recent_sessions: [{
      id: 'original-session', status: 'completed', created_at: '2026-11-04T12:00:00Z',
      summary: sessionFixture().summary, profile: null,
    }],
  };
}

function planFixture(minutes: 10 | 20 | 30 = 10): TimePlan {
  return { minutes, length: minutes === 10 ? 5 : minutes === 20 ? 10 : 20, estimated_seconds: minutes * 55, slots: [4, 7], selection: 'mixed', notice: null };
}

function apiFixture(): LearningExtrasApi {
  return {
    dashboard: vi.fn(async () => dashboardFixture()), progress: vi.fn(async () => progressFixture()),
    plan: vi.fn(async (minutes) => planFixture(minutes)), annotations: vi.fn(async () => []),
    annotate: vi.fn(async (body) => ({ favourite: false, manual: false, not_understood: false, cause: null, ...body })),
  };
}

describe('learning public HTTP boundary', () => {
  it('retains only public conditions and released journal fields in a cacheable dashboard', async () => {
    const wire = dashboardFixture();
    const payload = {
      ...wire,
      journal: wire.journal.map((entry) => ({
        ...entry, private_reason: 'secret-marker',
        task: { ...entry.task, expected_answer: 'hidden-marker', hints: ['secret-marker'], solution: ['hidden-marker'] },
        attempt: { ...entry.attempt, owner_id: 'secret-marker', idempotency_key: 'secret-marker' },
      })),
      favourites: [{ task: { ...wire.journal[0].task, expected_answer: 'hidden-marker' }, session_id: 'test-session' }],
      private_result: 'hidden-marker',
    };
    const fetcher = vi.fn(async () => Response.json(payload));
    vi.stubGlobal('fetch', fetcher);
    const result = await createLearningExtrasApi().dashboard();
    expect(fetcher).toHaveBeenCalledWith('/api/v1/learning/dashboard', expect.objectContaining({
      method: 'GET', credentials: 'same-origin', cache: 'no-store',
    }));
    expect(result.journal[0].attempt?.expected_answer).toBe('3');
    expect(JSON.stringify(result)).not.toMatch(/hidden-marker|secret-marker|private_result|owner_id|idempotency_key/);
  });

  it('accepts only released 0..13 assessment summaries and keeps their original profile', async () => {
    const payload = {
      ...dashboardFixture(), assessment_history: [{
        id: 'exam-one', mode: 'exam', status: 'completed', released_at: '2026-11-05T12:00:00Z', snapshot_at: '2026-11-05T11:59:00Z',
        score: 8, total: 13, elapsed_seconds: 1900, active_seconds: 1600, answered: 11, skipped: 2, format_errors: 0,
        profile_id: 'original-2026', profile_revision: 'r3',
        original_profile: { id: 'original-2026', title: 'Исходный профиль', year: 2026, revision: 'r3', answer: 'secret-marker' },
        rows: [{ expected: 'secret-marker' }], tasks: [{ solution: 'secret-marker' }],
      }],
    };
    vi.stubGlobal('fetch', vi.fn(async () => Response.json(payload)));
    const api = createLearningExtrasApi();
    const history = (await api.dashboard()).assessment_history;
    expect(history[0]).toMatchObject({ score: 8, total: 13, elapsed_seconds: 1900, profile: { id: 'original-2026', revision: 'r3' } });
    expect(JSON.stringify(history)).not.toContain('secret-marker');
    payload.assessment_history[0].status = 'active';
    await expect(api.dashboard()).rejects.toMatchObject({ code: 'invalid_learning_response' });
    payload.assessment_history[0].status = 'completed';
    payload.assessment_history[0].score = 14;
    await expect(api.dashboard()).rejects.toMatchObject({ code: 'invalid_learning_response' });
  });

  it('rejects an explicitly unreleased journal entry rather than returning its answers', async () => {
    const wire = dashboardFixture();
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ ...wire, journal: [{ ...wire.journal[0], released: false }] })));
    await expect(createLearningExtrasApi().dashboard()).rejects.toMatchObject({ code: 'invalid_learning_response' });
  });

  it('preserves changing practice counters and history links while discarding legacy answer-bearing data', async () => {
    const payload = { ...progressFixture(), mistakes: [{ expected_answer: 'hidden-marker' }], secret: 'hidden-marker' };
    vi.stubGlobal('fetch', vi.fn(async () => Response.json(payload)));
    const api = createLearningExtrasApi();
    const first = await api.progress();
    expect(first).toMatchObject({ independent_total: 2, independent_correct: 1, assisted_total: 3, corrections_total: 2, skipped_total: 4 });
    expect(practiceHistoryPath(first.recent_sessions[0])).toBe('/summary/original-session');
    payload.independent_correct = 2;
    expect(independentAccuracy(await api.progress())).toBe(100);
    expect(JSON.stringify(first)).not.toContain('hidden-marker');
  });

  it('preserves canonical progress metadata and frozen session profiles through the public boundary', async () => {
    const payload = {
      ...progressFixture(), algorithm_version: 'learning-v1', notice: 'Данные пересчитаны.', excluded_total: 2,
      recent_sessions: [{
        ...progressFixture().recent_sessions[0],
        profile: { id: 'original-2026', title: 'Исходный профиль', year: 2026, revision: 'r3', tasks: ['hidden-marker'] },
      }],
    };
    const api = createLearningExtrasApi(async () => payload);
    const result = await api.progress();
    expect(result).toMatchObject({ algorithm_version: 'learning-v1', notice: 'Данные пересчитаны.', excluded_total: 2 });
    expect(result.recent_sessions[0].profile).toEqual({ id: 'original-2026', title: 'Исходный профиль', year: 2026, revision: 'r3' });
    expect(JSON.stringify(result)).not.toContain('hidden-marker');
    payload.excluded_total = -1;
    await expect(api.progress()).rejects.toMatchObject({ code: 'invalid_learning_response' });
  });

  it.each([10, 20, 30] as const)('requests the %i-minute server plan and uses its mixed filters', async (minutes) => {
    const fetcher = vi.fn(async () => Response.json(planFixture(minutes)));
    vi.stubGlobal('fetch', fetcher);
    const plan = await createLearningExtrasApi().plan(minutes);
    expect(fetcher.mock.calls[0][0]).toBe(`/api/v1/learning/plan?minutes=${minutes}`);
    expect(mixedStartBody(plan)).toEqual({ mode: 'practice', slots: [4, 7], length: plan.length, selection: 'mixed', target_minutes: minutes });
    const query = new URLSearchParams(mixedPracticePath(plan).split('?')[1]);
    expect(Object.fromEntries(query)).toEqual({ slots: '4,7', length: String(plan.length), minutes: String(minutes), selection: 'mixed' });
  });

  it('posts only the chosen annotation fields, including explicit false and null, with the supplied UUID', async () => {
    const saved = { session_id: 'one', task_id: 'two', favourite: false, cause: null, manual: true, not_understood: true };
    const fetcher = vi.fn(async () => Response.json({ ...saved, owner_id: 'secret-marker' }));
    vi.stubGlobal('fetch', fetcher);
    const api = createLearningExtrasApi();
    expect(await api.annotate({ session_id: 'one', task_id: 'two', favourite: false, cause: null }, 'one-uuid')).toEqual(saved);
    expect(fetcher).toHaveBeenCalledWith('/api/v1/learning/annotations', expect.objectContaining({
      method: 'POST', cache: 'no-store', credentials: 'same-origin',
      headers: expect.objectContaining({ 'X-Requested-With': 'math-ege', 'Idempotency-Key': 'one-uuid' }),
      body: '{"session_id":"one","task_id":"two","favourite":false,"cause":null}',
    }));
  });

  it('keeps safe figures and rounding instructions without retaining drawing or grading extras', async () => {
    const wire = dashboardFixture();
    const figure = {
      description: 'Окружность и отрезок', x_min: -2, x_max: 2, y_min: -2, y_max: 2, axes: true,
      lines: [{ points: [{ x: 0, y: 0 }, { x: 1, y: 1 }], dashed: false, answer: 'hidden-marker' }],
      circles: [{ center: { x: 0, y: 0 }, radius: 1 }], labels: [{ x: 1, y: 1, text: 'A' }],
      svg: '<script>hidden-marker</script>',
    };
    const payload = { ...wire, journal: [{ ...wire.journal[0], task: {
      ...wire.journal[0].task, review_status: 'reviewed', slot_id: 'slot-probability', figure,
      rounding: { digits: 2, mode: 'half_up', instruction: 'Округлите до сотых.', expected: 'hidden-marker' },
    } }] };
    vi.stubGlobal('fetch', vi.fn(async () => Response.json(payload)));
    const result = await createLearningExtrasApi().dashboard();
    expect(result.journal[0].task).toMatchObject({
      slot_id: 'slot-probability', review_status: 'reviewed',
      figure: { description: 'Окружность и отрезок', circles: [{ center: { x: 0, y: 0 }, radius: 1 }] },
      rounding: { digits: 2, mode: 'half_up', instruction: 'Округлите до сотых.' },
    });
    expect(JSON.stringify(result)).not.toContain('hidden-marker');
    figure.circles[0].radius = 0;
    await expect(createLearningExtrasApi().dashboard()).rejects.toMatchObject({ code: 'invalid_learning_response' });
  });

  it('honours dashboard pagination and rejects a page that cannot advance', async () => {
    const wire = dashboardFixture();
    wire.pagination = { offset: 50, limit: 50, totals: { journal: 101, reviews: 1 } };
    wire.reviews[0].slot = null;
    const transport = vi.fn(async () => wire);
    const api = createLearningExtrasApi(transport);
    const result = await api.dashboard({ offset: 50 });
    expect(transport).toHaveBeenCalledWith('/learning/dashboard?offset=50&limit=50');
    expect(result.pagination).toEqual(wire.pagination);
    expect(result.reviews[0].slot).toBeNull();
    wire.pagination.limit = 0;
    await expect(api.dashboard({ offset: 50 })).rejects.toMatchObject({ code: 'invalid_learning_response' });
  });

  it('rejects impossible evidence totals instead of displaying a fabricated accuracy', async () => {
    const invalidCounts = { independent_total: 1, independent_correct: 2 };
    await expect(createLearningExtrasApi(async () => ({ ...dashboardFixture(), ...invalidCounts })).dashboard())
      .rejects.toMatchObject({ code: 'invalid_learning_response' });
    await expect(createLearningExtrasApi(async () => ({ ...progressFixture(), ...invalidCounts })).progress())
      .rejects.toMatchObject({ code: 'invalid_learning_response' });
  });

  it('reads saved flags independently of journal/favourite pages and follows annotation pagination', async () => {
    const saved = { session_id: 'test-session', task_id: sessionFixture().tasks[0].id, favourite: true, manual: true, not_understood: true, cause: 'graph' };
    const transport = vi.fn(async (path: string) => path.includes('offset=0') ? {
      annotations: [{ ...saved, task_id: 'other-task', owner_id: 'hidden-marker' }],
      pagination: { offset: 0, limit: 1, totals: { annotations: 2 } }, private_result: 'hidden-marker',
    } : { annotations: [saved], pagination: { offset: 1, limit: 1, totals: { annotations: 2 } } });
    const records = await createLearningExtrasApi(transport).annotations();
    expect(records.find((item) => item.task_id === saved.task_id)).toEqual(saved);
    expect(transport.mock.calls.map(([path]) => path)).toEqual([
      '/learning/export?offset=0&limit=100', '/learning/export?offset=1&limit=100',
    ]);
    expect(JSON.stringify(records)).not.toContain('hidden-marker');
    expect(annotationValues(records, 'test-session', saved.task_id)).toEqual({ favourite: true, manual: true, not_understood: true, cause: 'graph' });
    expect(annotationValues(records, 'another-session', saved.task_id)).toEqual({ favourite: false, manual: false, not_understood: false, cause: null });
  });

  it('does not infer absent annotations from a truncated or non-advancing export page', async () => {
    const transport = vi.fn(async () => ({ annotations: [], pagination: { offset: 0, limit: 100, totals: { annotations: 101 } } }));
    await expect(createLearningExtrasApi(transport).annotations()).rejects.toMatchObject({ code: 'invalid_learning_response' });
  });

  it('preserves the frozen profile of both journal and favourite tasks', async () => {
    const wire = dashboardFixture();
    const original = { profile_id: 'old-profile', profile_revision: 'r7' };
    const result = await createLearningExtrasApi(async () => ({ ...wire,
      journal: [{ ...wire.journal[0], ...original }],
      favourites: [{ ...wire.journal[0], ...original }],
    })).dashboard();
    expect(result.journal[0].profile).toMatchObject({ id: 'old-profile', revision: 'r7' });
    expect(result.favourites[0].profile).toEqual(result.journal[0].profile);
  });
});

describe('identity-scoped learning flow', () => {
  it('withholds cached private data until the current identity is confirmed, including failed refreshes', async () => {
    const actor = { id: 'A', kind: 'guest' as const, owner_ids: ['A'] };
    const remote = vi.fn(async () => actor);
    const manager = new IdentityManager(remote, actor);
    const api = apiFixture();
    const store = createLearningStore(api, { current: () => confirmedLearningOwner(manager) }, new EventTarget());
    const unsubscribe = manager.subscribe(store.syncIdentity);
    expect(confirmedLearningOwner(manager)).toBeNull();
    await store.dashboard.load();
    expect(api.dashboard).not.toHaveBeenCalled();
    await manager.refresh();
    await store.dashboard.load();
    expect(store.dashboard.getSnapshot().data).not.toBeNull();
    remote.mockRejectedValue(new Error('identity unavailable'));
    await manager.refresh();
    expect(manager.current()).toBe('A');
    expect(confirmedLearningOwner(manager)).toBeNull();
    expect(store.dashboard.getSnapshot().data).toBeNull();
    await store.dashboard.load();
    expect(api.dashboard).toHaveBeenCalledTimes(1);
    unsubscribe();
    store.dispose();
  });

  it('does not fetch private data for a visitor without an identity', async () => {
    const api = apiFixture();
    const store = createLearningStore(api, { current: () => null }, new EventTarget());
    await Promise.all([store.dashboard.load(), store.progress.load(), store.plan(10).load(), store.savedAnnotations.load()]);
    expect(api.dashboard).not.toHaveBeenCalled();
    expect(api.progress).not.toHaveBeenCalled();
    expect(api.plan).not.toHaveBeenCalled();
    expect(api.annotations).not.toHaveBeenCalled();
    expect(store.dashboard.getSnapshot()).toMatchObject({ ready: true, loading: false, data: null, error: null });
    store.dispose();
  });

  it('clears cached data and ignores an old response after A -> B -> A', async () => {
    let owner: string | null = 'A';
    const events = new EventTarget();
    const oldRequest = deferred<LearningDashboard>();
    const api = apiFixture();
    api.dashboard = vi.fn().mockReturnValueOnce(oldRequest.promise).mockResolvedValueOnce({ ...dashboardFixture(), recommendation: 'Fresh A' });
    const store = createLearningStore(api, { current: () => owner }, events);
    const oldLoad = store.dashboard.load();
    owner = 'B';
    events.dispatchEvent(new Event('math-ege:identity-change'));
    expect(store.dashboard.getSnapshot().data).toBeNull();
    owner = 'A';
    events.dispatchEvent(new Event('math-ege:identity-change'));
    await store.dashboard.load();
    oldRequest.resolve({ ...dashboardFixture(), recommendation: 'Old private A' });
    await oldLoad;
    expect(store.dashboard.getSnapshot().data?.recommendation).toBe('Fresh A');
    owner = null;
    events.dispatchEvent(new Event('math-ege:identity-change'));
    expect(store.dashboard.getSnapshot()).toMatchObject({ owner: null, data: null, ready: true });
    store.dispose();
  });

  it('finishes error/guest loads once instead of retrying on every render', async () => {
    const api = apiFixture();
    api.dashboard = vi.fn().mockRejectedValueOnce(new ApiError(0, 'network_error', 'offline')).mockRejectedValueOnce(new ApiError(401, 'unauthorized', 'expired'));
    const store = createLearningStore(api, { current: () => 'A' }, new EventTarget());
    await store.dashboard.load();
    await store.dashboard.load();
    await store.dashboard.load();
    expect(api.dashboard).toHaveBeenCalledTimes(1);
    expect(store.dashboard.getSnapshot()).toMatchObject({ ready: true, loading: false, error: expect.any(String) });
    await store.dashboard.retry();
    expect(store.dashboard.getSnapshot()).toMatchObject({ ready: true, loading: false, data: null, error: null });
    await store.dashboard.load();
    expect(api.dashboard).toHaveBeenCalledTimes(2);
    store.dispose();
  });

  it('stops annotation pagination and rejects its partial data after A -> B -> A', async () => {
    let owner = 'A';
    const events = new EventTarget();
    const page = deferred<unknown>();
    const transport = vi.fn(() => page.promise);
    const api = { ...apiFixture(), annotations: createLearningExtrasApi(transport).annotations };
    const store = createLearningStore(api, { current: () => owner }, events);
    const load = store.savedAnnotations.load();
    owner = 'B';
    events.dispatchEvent(new Event('math-ege:identity-change'));
    owner = 'A';
    events.dispatchEvent(new Event('math-ege:identity-change'));
    page.resolve({ annotations: [{ session_id: 'old-session', task_id: 'old-task', favourite: true, manual: false, not_understood: false, cause: null }],
      pagination: { offset: 0, limit: 1, totals: { annotations: 2 } } });
    await load;
    expect(transport).toHaveBeenCalledTimes(1);
    expect(store.savedAnnotations.getSnapshot().data).toBeNull();
    store.dispose();
  });
});

describe('annotation mutation flow', () => {
  it('serializes a double click and retries a lost response with the same frozen body and UUID', async () => {
    const lost = deferred<void>();
    const api = { annotate: vi.fn().mockReturnValueOnce(lost.promise).mockResolvedValueOnce({ session_id: 'session', task_id: 'task', favourite: true, cause: 'graph', manual: true, not_understood: false }) };
    const saved = vi.fn();
    const writer = new AnnotationWriter('session', 'task', api, { current: () => 'A' }, saved, () => 'stable-uuid');
    const first = writer.save({ favourite: true });
    const double = writer.save({ favourite: false });
    expect(api.annotate).toHaveBeenCalledTimes(1);
    lost.reject(new ApiError(0, 'network_error', 'offline'));
    await Promise.all([first, double]);
    expect(writer.getSnapshot()).toMatchObject({ saving: false, saved: false, pending: { key: 'stable-uuid', body: { favourite: true } } });
    await writer.retry();
    expect(api.annotate.mock.calls).toEqual([
      [{ session_id: 'session', task_id: 'task', favourite: true }, 'stable-uuid'],
      [{ session_id: 'session', task_id: 'task', favourite: true }, 'stable-uuid'],
    ]);
    expect(writer.getSnapshot()).toMatchObject({ saved: true, pending: null, confirmed: { favourite: true, cause: 'graph', manual: true, not_understood: false } });
    expect(saved).toHaveBeenCalledTimes(1);
  });

  it('drops pending annotation state and late completion when the identity changes', async () => {
    let owner = 'A';
    const events = new EventTarget();
    const pending = deferred<SavedAnnotation>();
    const api = apiFixture();
    api.annotate = vi.fn(() => pending.promise);
    const store = createLearningStore(api, { current: () => owner }, events);
    const writer = store.annotation('session', 'task');
    const save = writer.save({ cause: 'calculation', manual: true });
    owner = 'B';
    events.dispatchEvent(new Event('math-ege:identity-change'));
    pending.resolve({ session_id: 'session', task_id: 'task', cause: 'calculation', manual: true, favourite: false, not_understood: false });
    await save;
    expect(writer.getSnapshot()).toMatchObject({ saved: false, pending: null, confirmed: {} });
    expect(api.dashboard).not.toHaveBeenCalled();
    expect(store.annotation('session', 'task')).not.toBe(writer);
    await writer.save({ favourite: true });
    expect(api.annotate).toHaveBeenCalledTimes(1);
    store.dispose();
  });
});

describe('learning view models', () => {
  it('links an analogue to the exact family and never turns an empty family into a number-only analogue', () => {
    const path = familyPracticePath(4, 'probability/a & b');
    const query = new URLSearchParams(path!.split('?')[1]);
    expect(path).toMatch(/^\/practice\?/);
    expect(query.get('slots')).toBe('4');
    expect(query.get('families')).toBe('probability/a & b');
    expect(familyPracticePath(4, '')).toBeNull();
  });

  it('resolves renumbered tasks by stable position and keeps retired or ambiguous positions unlinked', () => {
    const dashboard = dashboardFixture();
    const task = { ...sessionFixture().tasks[0], slot: 1, slot_id: 'slot-probability' };
    expect(currentTaskSlot(task, dashboard)).toBe(4);
    expect(currentTaskSlot({ ...task, slot_id: 'retired-slot' }, dashboard)).toBeNull();
    expect(familyPracticePath(null, task.family_id)).toBeNull();
    const legacy = { ...task, slot_id: null, skill_ids: ['probability'] };
    expect(currentTaskSlot(legacy, dashboard)).toBe(4);
    dashboard.slots.push({ ...dashboard.slots[0], slot_id: 'other-position', number: 7 });
    expect(currentTaskSlot(legacy, dashboard)).toBeNull();
  });

  it('keeps URL page offsets inside the supported backend range', () => {
    expect(pageOffset('50')).toBe(50);
    for (const value of [null, '-1', '2.5', 'Infinity', '1000001']) expect(pageOffset(value)).toBe(0);
  });

  it('does not guess a theory cause for repeated or assisted answers and preserves manual flags', () => {
    const entry = dashboardFixture().journal[0];
    entry.attempt = { ...attemptFixture(), first_attempt: false, independent: false, assisted: true };
    entry.manual = true;
    entry.not_understood = true;
    expect(entryDescription(entry)).toContain('Повторный ответ');
    expect(annotationValues([{ session_id: entry.session_id, task_id: entry.task.id, favourite: true, cause: null, manual: true, not_understood: true }], entry.session_id, entry.task.id)).toEqual({ favourite: true, cause: null, manual: true, not_understood: true });
    entry.attempt.first_attempt = true;
    expect(entryDescription(entry)).toContain('Ответ с помощью');
    expect(entry.cause).toBeNull();
  });

  it('uses server mastery and evidence coverage without deriving readiness from a success ratio', () => {
    const dashboard = dashboardFixture();
    const slots = coverageSlots(dashboard);
    expect(slots[0]).toMatchObject({ status: 'Освоено', attempts: 24, correct: 21, covered_skills: 2, total_skills: 2 });
    expect(independentAccuracy({ independent_total: 0, independent_correct: 0 })).toBeNull();
    expect(independentAccuracy({ independent_total: 5, independent_correct: 3 })).toBe(60);
    expect(coverageSlots(null)).toEqual([]);
  });

  it('shows due reviews in date order and does not relabel a future review as due', () => {
    const review = dashboardFixture().reviews[0];
    const reviews = [review, { ...review, family_id: 'older', due_at: '2026-11-04T12:00:00Z', overdue: true }];
    expect(dueReviews(reviews, Date.parse('2026-11-05T12:00:00Z')).map((item) => item.family_id)).toEqual(['older']);
  });

  it('keeps historical profile context rather than substituting the current course profile', () => {
    expect(originalProfileLabel({ id: 'old', title: 'Исходный профиль', year: 2026, revision: '2' })).toBe('Исходный профиль, 2026, редакция 2');
    expect(originalProfileLabel(null)).toContain('не указан');
  });
});
