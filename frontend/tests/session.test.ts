import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../src/api/client';
import { SessionController } from '../src/learning/session-controller';
import { createRecord } from '../src/learning/model';
import { apiFixture, attemptFixture, deferred, memoryStorage, sessionFixture } from './fixtures';

afterEach(() => { vi.useRealTimers(); });

describe('local-first revision stream', () => {
  it('keeps newer input while an older server response is in flight', async () => {
    vi.useFakeTimers();
    const api = apiFixture();
    const response = deferred<{ draft_revision: number }>();
    api.draft = vi.fn(() => response.promise);
    const memory = memoryStorage();
    const controller = new SessionController('test-session', api, memory.store);
    await controller.load();
    controller.edit('12');
    const flush = controller.sync.flush();
    await vi.advanceTimersByTimeAsync(0);
    expect(api.draft).toHaveBeenCalledWith('test-session', expect.objectContaining({ answer: '12', expected_revision: 0 }));
    controller.edit('12,5');
    response.resolve({ draft_revision: 1 });
    await flush;
    expect(controller.getSnapshot().record?.drafts['task-1']).toMatchObject({ answer: '12,5', version: 2, synced_version: 1 });
    expect(memory.read()?.drafts['task-1'].answer).toBe('12,5');
  });

  it('restores unsynced text instead of replacing it during GET loading', async () => {
    vi.useFakeTimers();
    const local = createRecord(sessionFixture());
    local.current_index = 1;
    local.drafts['task-2'] = { answer: '−12,50', active_seconds: 13, version: 2, synced_version: 0 };
    const controller = new SessionController(local.session.id, apiFixture(), memoryStorage(local).store);
    await controller.load();
    expect(controller.getSnapshot().record?.drafts['task-2'].answer).toBe('−12,50');
    expect(controller.getSnapshot().record?.current_index).toBe(1);
  });

  it('marks a revision conflict without changing local text', async () => {
    vi.useFakeTimers();
    const api = apiFixture();
    api.draft = vi.fn(async () => { throw new ApiError(409, 'draft_conflict', 'Conflict'); });
    const controller = new SessionController('test-session', api, memoryStorage().store);
    await controller.load();
    controller.edit('3,5');
    await controller.sync.flush();
    expect(controller.getSnapshot().conflict).toBe(true);
    expect(controller.getSnapshot().record?.drafts['task-1'].answer).toBe('3,5');
  });

  it('requires explicit confirmation when the loaded remote revision is newer', async () => {
    vi.useFakeTimers();
    const local = createRecord(sessionFixture());
    local.drafts['task-1'] = { answer: 'mine', active_seconds: 1, version: 1, synced_version: 0 };
    const api = apiFixture();
    api.session = vi.fn(async () => ({ ...sessionFixture(), draft_revision: 2, drafts: { 'task-1': { answer: 'remote', active_seconds: 1 } } }));
    const controller = new SessionController('test-session', api, memoryStorage(local).store);
    await controller.load();
    expect(controller.getSnapshot().conflict).toBe(true);
    expect(controller.getSnapshot().record?.drafts['task-1'].answer).toBe('mine');
    expect(api.draft).not.toHaveBeenCalled();
  });

  it('sends edits within one second using the latest raw input', async () => {
    vi.useFakeTimers();
    const api = apiFixture();
    const controller = new SessionController('test-session', api, memoryStorage().store);
    await controller.load();
    controller.edit('0002.50');
    await vi.advanceTimersByTimeAsync(700);
    expect(api.draft).toHaveBeenCalledWith('test-session', { task_id: 'task-1', answer: '0002.50', active_seconds: 0, expected_revision: 0 });
  });
});

describe('durable idempotent attempts', () => {
  it('persists before sending and blocks a double click', async () => {
    vi.useFakeTimers();
    const api = apiFixture();
    const memory = memoryStorage();
    const response = deferred<ReturnType<typeof attemptFixture>>();
    api.attempt = vi.fn(async (_id, body, key) => {
      expect(memory.read()?.pending_attempt).toEqual({ key, body });
      return response.promise;
    });
    const controller = new SessionController('test-session', api, memory.store);
    await controller.load();
    controller.edit('2,50');
    const first = controller.actions.submit();
    const second = controller.actions.submit();
    await vi.advanceTimersByTimeAsync(0);
    expect(api.attempt).toHaveBeenCalledTimes(1);
    response.resolve(attemptFixture());
    await Promise.all([first, second]);
    expect(controller.getSnapshot().record?.pending_attempt).toBeNull();
    expect(controller.getSnapshot().record?.session.attempts).toHaveLength(1);
  });

  it('retries the same UUID and exact body after a reload and a lost response', async () => {
    vi.useFakeTimers();
    const memory = memoryStorage();
    const api = apiFixture();
    api.attempt = vi.fn(async () => { throw new ApiError(0, 'network_error', 'No connection'); });
    const first = new SessionController('test-session', api, memory.store);
    await first.load();
    first.edit('2,50');
    first.recordTime('task-1', 8);
    await first.actions.submit();
    const pending = structuredClone(memory.read()?.pending_attempt);
    expect(pending?.body).toEqual({ task_id: 'task-1', answer: '2,50', active_seconds: 8, skipped: false });
    const replayApi = apiFixture();
    const reloaded = new SessionController('test-session', replayApi, memory.store);
    await reloaded.load();
    reloaded.edit('should not replace pending text');
    await reloaded.actions.submit();
    expect(replayApi.attempt).toHaveBeenCalledWith('test-session', pending?.body, pending?.key);
    expect(reloaded.getSnapshot().record?.drafts['task-1'].answer).toBe('2,50');
  });

  it('keeps raw invalid input, clears only the rejected pending event, and adds no attempt', async () => {
    vi.useFakeTimers();
    const api = apiFixture();
    api.attempt = vi.fn(async () => { throw new ApiError(422, 'invalid_answer', 'Wrong format', 'answer'); });
    const controller = new SessionController('test-session', api, memoryStorage().store);
    await controller.load();
    controller.edit('1/0');
    await controller.actions.submit();
    expect(api.attempt).toHaveBeenCalledTimes(1);
    expect(controller.getSnapshot().record?.drafts['task-1'].answer).toBe('1/0');
    expect(controller.getSnapshot().record?.session.attempts).toHaveLength(0);
    expect(controller.getSnapshot().record?.pending_attempt).toBeNull();
    expect(controller.getSnapshot().formError?.status).toBe(422);
  });

  it('cannot submit before a pending record is durably saved', async () => {
    vi.useFakeTimers();
    const api = apiFixture();
    const memory = memoryStorage();
    const controller = new SessionController('test-session', api, memory.store);
    await controller.load();
    controller.edit('2,50');
    memory.store.saveSession = vi.fn(async () => { throw new Error('Quota exceeded'); });
    await controller.actions.submit();
    expect(api.attempt).not.toHaveBeenCalled();
    expect(controller.getSnapshot().storageError).not.toBeNull();
    await controller.actions.submit();
    expect(api.attempt).not.toHaveBeenCalled();
  });

  it('always sends an empty answer for skip without erasing the visible raw draft', async () => {
    vi.useFakeTimers();
    const api = apiFixture();
    const controller = new SessionController('test-session', api, memoryStorage().store);
    await controller.load();
    controller.edit('not submitted');
    await controller.actions.submit(true);
    expect(api.attempt).toHaveBeenCalledWith('test-session', expect.objectContaining({ answer: '', skipped: true }), expect.any(String));
    expect(controller.getSnapshot().record?.drafts['task-1'].answer).toBe('not submitted');
  });

  it('preserves the finish UUID after a lost result and never turns a draft into an attempt', async () => {
    vi.useFakeTimers();
    const api = apiFixture();
    const memory = memoryStorage();
    api.finish = vi.fn(async () => { throw new ApiError(0, 'network_error', 'No connection'); });
    const controller = new SessionController('test-session', api, memory.store);
    await controller.load();
    controller.edit('draft only');
    await controller.actions.finish();
    const key = controller.getSnapshot().record?.finish_key;
    expect(api.attempt).not.toHaveBeenCalled();
    expect(controller.getSnapshot().record?.pending_finish).toBe(true);
    const replayApi = apiFixture();
    const reloaded = new SessionController('test-session', replayApi, memory.store);
    await reloaded.load();
    await reloaded.actions.finish();
    expect(replayApi.finish).toHaveBeenCalledWith('test-session', key);
    expect(reloaded.getSnapshot().record?.session.status).toBe('completed');
  });
});
