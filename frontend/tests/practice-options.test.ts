import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../src/api/client';
import { practiceOptions } from '../src/learning/practice-options';
import { SessionController } from '../src/learning/session-controller';
import { createRecord } from '../src/learning/model';
import { apiFixture, memoryStorage, sessionFixture } from './fixtures';

afterEach(() => { vi.useRealTimers(); });

describe('practice route options', () => {
  it('preserves exact family, skill, time and explicit-repeat intent from a link', () => {
    expect(practiceOptions(new URLSearchParams('slots=6,6,7&families=distribution-variance&skills=rv-variance&length=10&minutes=20&selection=mixed&until_stopped=true&repeat=task-6'))).toEqual({
      slots: [6, 7], length: 10, mode: 'practice', family_ids: ['distribution-variance'],
      skill_ids: ['rv-variance'], target_minutes: 20, selection: 'mixed', until_stopped: true,
      repeat_task_id: 'task-6', difficulty: null,
    });
  });
  it('does not interpret unsupported durations or coercive length strings as controls', () => {
    const options = practiceOptions(new URLSearchParams('length=10oops&minutes=11&difficulty=9'));
    expect(options.length).toBe(5);
    expect(options.target_minutes).toBeNull();
    expect(options.difficulty).toBeNull();
  });
});

describe('append-only continued practice', () => {
  it('retains the pending UUID and first appended position after a lost response and reload', async () => {
    vi.useFakeTimers();
    const session = sessionFixture();
    session.options = { slots: [1, 2], length: 5, mode: 'practice', until_stopped: true };
    const memory = memoryStorage(createRecord(session));
    const api = apiFixture();
    api.session = vi.fn(async () => session);
    api.extend = vi.fn(async () => { throw new ApiError(0, 'network_error', 'offline'); });
    const first = new SessionController(session.id, api, memory.store);
    await first.load();
    await first.actions.extend();
    const key = memory.read()?.extension_key;
    expect(key).toBeTruthy();
    await first.actions.submit(true);
    await first.actions.hint(1);
    expect(api.attempt).not.toHaveBeenCalled();
    expect(api.hint).not.toHaveBeenCalled();
    const remote = {
      ...session, draft_revision: 1,
      tasks: [...session.tasks, ...session.tasks.map((task) => ({ ...task, id: `${task.id}-next` }))],
    };
    const replay = apiFixture();
    replay.session = vi.fn(async () => remote);
    replay.extend = vi.fn(async () => remote);
    const restored = new SessionController(session.id, replay, memory.store);
    await restored.load();
    await restored.retry();
    expect(replay.extend).toHaveBeenCalledWith(session.id, key);
    expect(restored.getSnapshot().record?.current_index).toBe(session.tasks.length);
    expect(restored.getSnapshot().record?.extension_key).toBeNull();
    expect(restored.getSnapshot().record?.session.tasks.slice(0, 2)).toEqual(session.tasks);
  });
});
