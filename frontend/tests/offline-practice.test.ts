import { IDBFactory } from 'fake-indexeddb';
import { openDB } from 'idb';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { OfflineRuntime } from '../src/offline/practice';
import type { OfflineCourse, OfflineTask, StartBody } from '../src/offline/types';

const now = Date.UTC(2026, 10, 6, 12);
const start: StartBody = { slots: [1], length: 5, mode: 'practice' };
const key = () => crypto.randomUUID();

function course(count = 6): OfflineCourse {
  const tasks: OfflineTask[] = Array.from({ length: count }, (_, index) => ({
    id: `local-test-${index}`, revision: '1', slot: 1, slot_id: 'slot-1', topic: 'Дроби',
    title: `Задача ${index + 1}`, statement: `Найдите половину числа ${index + 1}.`,
    formula: null, table: null, figure: null, rounding: null, skill_ids: ['fractions'],
    family_id: `half-${index % 2}`, estimated_seconds: 120, review_status: 'demo',
    hint_count: 3, answer: '0,5', hints: ['Выберите действие.', 'Разделите на два.', 'Проверьте ответ.'],
    solution: ['Делим на два.', 'Получаем 0,5.'], profile_id: 'test-profile', difficulty: 1,
    generation: null, instance_key: (index + 1).toString(16).padStart(64, '0'),
    source: { author: 'test', origin: 'test', rights: 'test', reviewed_by: null },
  }));
  return {
    version: '1', package_revision: 'test-course-1', tasks, lessons: [],
    profile: { id: 'test-profile', year: 2027, title: 'Тестовый профиль', status: 'draft',
      revision: '1', verified_at: '2026-11-06', verification_note: 'Демонстрация.', source_urls: [],
      demo_mode: true, bank_size: count, slots: [{ number: 1, id: 'slot-1', title: 'Дроби', level: 'Б',
        summary: 'Дроби', skills: [{ id: 'fractions', title: 'Дроби' }], available_tasks: count, lesson_id: 'test-lesson' }] },
  };
}

beforeEach(() => {
  vi.stubGlobal('indexedDB', new IDBFactory());
  vi.spyOn(Date, 'now').mockReturnValue(now);
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('device-only practice', () => {
  it('keeps the same isolated owner after closing and reopening without inventing history', async () => {
    const runtime = new OfflineRuntime(course());
    const state = await runtime.state();
    expect(state).toEqual({ owner: expect.stringMatching(/^[0-9a-f-]{36}$/), active_session_id: null, sessions: [] });
    await runtime.close();
    const reopened = new OfflineRuntime(course());
    expect(await reopened.state()).toEqual(state);
    expect((await reopened.progress()).independent_total).toBe(0);
    await reopened.close();
  });

  it('atomically issues frozen snapshots and replays the same start key without creating a second session', async () => {
    const source = course();
    const runtime = new OfflineRuntime(source);
    const operation = key();
    const issued = await runtime.start(start, operation);
    expect(issued.tasks).toHaveLength(5);
    expect(new Set(issued.tasks.map((task) => task.id)).size).toBe(5);
    expect(issued.profile).toMatchObject({ id: 'test-profile', revision: '1', status: 'draft' });
    expect(issued.tasks.every((task) => !('answer' in task) && !('hints' in task))).toBe(true);
    expect(await runtime.start({ ...start }, operation)).toEqual(issued);
    await expect(runtime.start({ ...start, length: 10 }, operation)).rejects.toMatchObject({ code: 'idempotency_conflict' });
    source.tasks.forEach((task) => { task.statement = 'Обновлённое условие.'; task.answer = '7'; });
    source.profile.revision = '2';
    await runtime.close();
    const upgraded = new OfflineRuntime(source);
    expect(await upgraded.session(issued.id)).toEqual(issued);
    expect((await upgraded.state()).sessions).toHaveLength(1);
    expect((await upgraded.state()).active_session_id).toBe(issued.id);
    await upgraded.close();
  });

  it('rejects format without an attempt, checks the frozen reference, and preserves the first error after correction', async () => {
    const source = course();
    const runtime = new OfflineRuntime(source);
    const session = await runtime.start(start, key());
    const taskId = session.tasks[0].id;
    const operation = key();
    const body = { task_id: taskId, answer: '1/0', active_seconds: 12, skipped: false };
    await expect(runtime.attempt(session.id, body, operation)).rejects.toMatchObject({ code: 'invalid_answer_format' });
    expect((await runtime.session(session.id)).attempts).toEqual([]);
    const first = await runtime.attempt(session.id, { ...body, answer: '999' }, operation);
    expect(first).toMatchObject({ raw_answer: '999', correct: false, first_attempt: true, independent: true, assisted: false });
    expect(await runtime.attempt(session.id, { ...body, answer: '999' }, operation)).toEqual(first);
    await expect(runtime.attempt(session.id, { ...body, answer: '1/2' }, operation)).rejects.toMatchObject({ code: 'idempotency_conflict' });
    await runtime.close();
    source.tasks.forEach((task) => { task.answer = '7'; });
    const upgraded = new OfflineRuntime(source);
    const correction = await upgraded.attempt(session.id, { ...body, answer: '1/2', active_seconds: 20 }, key());
    expect(correction).toMatchObject({ correct: true, normalized_answer: '0,5', expected_answer: '0,5', first_attempt: false, independent: false, assisted: true });
    expect((await upgraded.session(session.id)).attempts[0]).toEqual(first);
    expect((await upgraded.progress())).toMatchObject({ independent_total: 1, independent_correct: 0, corrections_total: 1 });
    await upgraded.close();
  });

  it('restores the selected task and draft, handles optimistic conflicts, and never reduces active time', async () => {
    const runtime = new OfflineRuntime(course());
    const session = await runtime.start(start, key());
    const body = { task_id: session.tasks[2].id, answer: '1/0', active_seconds: 15, expected_revision: 0 };
    expect(await runtime.draft(session.id, body)).toEqual({ draft_revision: 1 });
    expect(await runtime.draft(session.id, body)).toEqual({ draft_revision: 1 });
    await expect(runtime.draft(session.id, { ...body, answer: '7' })).rejects.toMatchObject({ code: 'draft_conflict' });
    await runtime.position(session.id, 2);
    await runtime.close();
    const reopened = new OfflineRuntime(course());
    const stored = await reopened.session(session.id);
    expect(stored.current_index).toBe(2);
    expect(stored.drafts[body.task_id]).toEqual({ answer: '1/0', active_seconds: 15 });
    expect(stored.attempts).toEqual([]);
    await reopened.draft(session.id, { ...body, answer: '1/2', active_seconds: 2, expected_revision: 1 });
    expect((await reopened.session(session.id)).drafts[body.task_id]).toEqual({ answer: '1/2', active_seconds: 15 });
    await expect(reopened.position(session.id, 99)).rejects.toMatchObject({ code: 'invalid_position' });
    await reopened.close();
  });

  it('persists progressive hints and solutions before returning and labels the first assisted answer honestly', async () => {
    const runtime = new OfflineRuntime(course());
    const session = await runtime.start(start, key());
    const taskId = session.tasks[0].id;
    await expect(runtime.hint(session.id, taskId, 3)).rejects.toMatchObject({ code: 'hint_order' });
    const hint = await runtime.hint(session.id, taskId, 1);
    expect(hint).toEqual({ level: 1, text: 'Выберите действие.' });
    expect(await runtime.hint(session.id, taskId, 1)).toEqual(hint);
    await runtime.close();
    const reopened = new OfflineRuntime(course());
    expect((await reopened.session(session.id)).help[taskId].hints).toEqual([hint]);
    await reopened.hint(session.id, taskId, 2);
    await reopened.hint(session.id, taskId, 3);
    expect(await reopened.solution(session.id, taskId)).toEqual({ answer: '0,5', steps: ['Делим на два.', 'Получаем 0,5.'] });
    const attempt = await reopened.attempt(session.id, { task_id: taskId, answer: '1/2', active_seconds: 10, skipped: false }, key());
    expect(attempt).toMatchObject({ correct: true, first_attempt: true, assisted: true, independent: false });
    expect(await reopened.progress()).toMatchObject({ independent_total: 0, independent_correct: 0, assisted_total: 1 });
    await reopened.close();
  });

  it('freezes completion and explicit skips without grading an unsubmitted draft or deleting history', async () => {
    const runtime = new OfflineRuntime(course());
    const session = await runtime.start(start, key());
    await runtime.attempt(session.id, { task_id: session.tasks[0].id, answer: '', skipped: true, active_seconds: 3 }, key());
    await runtime.draft(session.id, { task_id: session.tasks[1].id, answer: '0', active_seconds: 15,
      expected_revision: (await runtime.session(session.id)).draft_revision });
    const operation = key();
    const completed = await runtime.finish(session.id, operation);
    expect(completed).toMatchObject({ status: 'completed', summary: { total: 5, answered: 0, skipped: 1, independent_total: 0, active_seconds: 18 } });
    expect(completed.attempts).toHaveLength(1);
    expect(completed.drafts[session.tasks[1].id].answer).toBe('0');
    expect(await runtime.finish(session.id, operation)).toEqual(completed);
    expect(await runtime.finish(session.id, key())).toEqual(completed);
    await expect(runtime.attempt(session.id, { task_id: session.tasks[1].id, answer: '0,5', skipped: false, active_seconds: 20 }, key()))
      .rejects.toMatchObject({ code: 'session_completed' });
    await expect(runtime.hint(session.id, session.tasks[1].id, 1)).rejects.toMatchObject({ code: 'session_completed' });
    await expect(runtime.position(session.id, 2)).rejects.toMatchObject({ code: 'session_completed' });
    expect((await runtime.state()).active_session_id).toBeNull();
    expect((await runtime.state()).sessions).toEqual([completed]);
    await runtime.close();
    const reopened = new OfflineRuntime(course());
    expect(await reopened.session(session.id)).toEqual(completed);
    await reopened.close();
  });

  it('excludes aliases for 30 days, exposes exhaustion, and marks boundary and explicit repeats as familiar', async () => {
    const source = course(1);
    source.tasks.push({ ...source.tasks[0], id: 'local-alias', revision: '2' });
    const runtime = new OfflineRuntime(source);
    const issued = await runtime.start(start, key());
    expect(issued.tasks).toHaveLength(1);
    expect(issued.notice).toContain('1 из 5');
    await expect(runtime.start(start, key())).rejects.toMatchObject({ code: 'bank_exhausted' });
    vi.mocked(Date.now).mockReturnValue(now + 30 * 86_400_000 - 1);
    await expect(runtime.start(start, key())).rejects.toMatchObject({ code: 'bank_exhausted' });
    vi.mocked(Date.now).mockReturnValue(now + 30 * 86_400_000);
    const boundary = await runtime.start(start, key());
    expect(boundary.tasks).toHaveLength(1);
    expect(boundary.notice).toContain('встречалась раньше');
    const answer = { task_id: boundary.tasks[0].id, answer: '0,5', active_seconds: 0, skipped: false };
    expect(await runtime.attempt(boundary.id, answer, key())).toMatchObject({ correct: true, independent: false });
    const repeated = await runtime.start({ ...start, repeat_task_id: 'local-alias' }, key());
    expect(repeated.tasks[0].id).toBe('local-alias');
    expect(repeated.notice).toContain('Явный повтор');
    expect(await runtime.attempt(repeated.id, { ...answer, task_id: 'local-alias' }, key()))
      .toMatchObject({ correct: true, assisted: true, independent: false });
    expect((await runtime.state()).sessions).toHaveLength(3);
    expect((await runtime.progress()).independent_total).toBe(0);
    await runtime.close();
  });

  it('serializes concurrent starts and attempts from two windows under one device owner and operation key', async () => {
    const first = new OfflineRuntime(course());
    const second = new OfflineRuntime(course());
    const operation = key();
    const [a, b] = await Promise.all([first.start(start, operation), second.start({ ...start }, operation)]);
    expect(a).toEqual(b);
    expect((await first.state()).owner).toBe((await second.state()).owner);
    expect((await first.state()).sessions).toHaveLength(1);
    const body = { task_id: a.tasks[0].id, answer: '0,5', active_seconds: 1, skipped: false };
    const attemptKey = key();
    const [one, two] = await Promise.all([first.attempt(a.id, body, attemptKey), second.attempt(a.id, body, attemptKey)]);
    expect(one).toEqual(two);
    await expect(second.attempt(a.id, { ...body, answer: '7' }, attemptKey)).rejects.toMatchObject({ code: 'idempotency_conflict' });
    expect((await first.session(a.id)).attempts).toEqual([one]);
    expect((await second.progress())).toMatchObject({ independent_total: 1, independent_correct: 1 });
    await Promise.all([first.close(), second.close()]);
  });

  it('leaves online ownership, legacy snapshots, and pending operation namespaces byte-for-byte unchanged', async () => {
    const online = await openDB('math-ege-learning-v1', 2, {
      upgrade(db) { for (const store of ['sessions', 'lessons', 'meta', 'scoped_sessions', 'scoped_meta', 'revision_lessons']) db.createObjectStore(store); },
    });
    const owner = key();
    const frozen = '{"owner":"server","revision":"immutable","draft":"1/0"}';
    const pending = '{"key":"original-uuid","body":{"length":10}}';
    await online.put('sessions', frozen, 'original-task');
    await online.put('scoped_sessions', frozen, [owner, 'original-session']);
    await online.put('scoped_meta', pending, [owner, 'pending_start']);
    const runtime = new OfflineRuntime(course());
    const issued = await runtime.start(start, key());
    expect((await runtime.state()).owner).not.toBe(owner);
    await runtime.finish(issued.id, key());
    expect(await online.get('sessions', 'original-task')).toBe(frozen);
    expect(await online.get('scoped_sessions', [owner, 'original-session'])).toBe(frozen);
    expect(await online.get('scoped_meta', [owner, 'pending_start'])).toBe(pending);
    expect((await runtime.state()).sessions).toHaveLength(1);
    online.close();
    await runtime.close();
  });

  it('rolls back issuance and its exposure when the durable operation write fails, then retries the same key', async () => {
    const runtime = new OfflineRuntime(course(5));
    await runtime.state();
    const add = IDBObjectStore.prototype.add;
    const fault = vi.spyOn(IDBObjectStore.prototype, 'add').mockImplementation(function (this: IDBObjectStore, value: unknown, id?: IDBValidKey) {
      if (this.name === 'operations') throw new DOMException('Storage quota exceeded', 'QuotaExceededError');
      return add.call(this, value, id);
    });
    const operation = key();
    await expect(runtime.start(start, operation)).rejects.toMatchObject({ code: 'storage_unavailable' });
    expect(await runtime.state()).toMatchObject({ active_session_id: null, sessions: [] });
    fault.mockRestore();
    const issued = await runtime.start(start, operation);
    expect(issued.tasks).toHaveLength(5);
    expect(await runtime.start(start, operation)).toEqual(issued);
    await runtime.close();
  });
});
