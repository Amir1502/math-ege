import type { LearningApi } from '../src/api/client';
import type { Attempt, LearningSession } from '../src/api/types';
import type { LearningStorage } from '../src/storage/database';
import type { SessionRecord } from '../src/learning/model';
import { vi } from 'vitest';

export function sessionFixture(): LearningSession {
  return {
    id: 'test-session', profile_id: 'test-profile', mode: 'practice', status: 'active',
    created_at: '2026-11-05T12:00:00Z', completed_at: null, current_index: 0,
    requested_length: 5, notice: null, draft_revision: 0,
    tasks: [1, 2].map((slot) => ({
      id: `task-${slot}`, revision: '1', slot, topic: 'Тестовый номер', title: 'Тестовое условие',
      statement: 'Тестовый контент существует только в тестах.', formula: null, table: null,
      skill_ids: ['skill'], family_id: 'family', estimated_seconds: 60, review_status: 'demo', hint_count: 3,
    })),
    attempts: [], drafts: {}, help: {},
    summary: { total: 2, answered: 0, independent_total: 0, independent_correct: 0, assisted: 0, corrections: 0, skipped: 0, active_seconds: 0 },
  };
}

export function attemptFixture(): Attempt {
  return {
    id: 'attempt-one', task_id: 'task-1', raw_answer: '2,50', normalized_answer: '2,5',
    correct: false, assisted: false, first_attempt: true, independent: true, skipped: false,
    active_seconds: 8, created_at: '2026-11-05T12:00:00Z', expected_answer: '3', solution: ['Тестовый разбор.'],
  };
}

export function apiFixture(): LearningApi {
  return {
    profile: vi.fn(), lesson: vi.fn(), progress: vi.fn(), export: vi.fn(), guest: vi.fn(), start: vi.fn(),
    session: vi.fn(async () => sessionFixture()), draft: vi.fn(async () => ({ draft_revision: 1 })),
    attempt: vi.fn(async () => attemptFixture()), hint: vi.fn(async (_id, _taskId, level) => ({ level, text: 'Подсказка.' })),
    solution: vi.fn(async () => ({ answer: '3', steps: ['Тестовый разбор.'] })),
    finish: vi.fn(async () => ({ ...sessionFixture(), status: 'completed', completed_at: '2026-11-05T12:00:01Z' })),
  };
}

export function memoryStorage(initial?: SessionRecord) {
  let saved = initial ? structuredClone(initial) : undefined;
  const store: LearningStorage = {
    session: vi.fn(async () => saved ? structuredClone(saved) : undefined),
    saveSession: vi.fn(async (record) => { saved = structuredClone(record); }),
    journal: vi.fn(), setActive: vi.fn(async () => undefined), active: vi.fn(async () => null),
    lesson: vi.fn(async () => undefined), saveLesson: vi.fn(async () => undefined),
    pendingStart: vi.fn(async () => null), savePendingStart: vi.fn(async () => undefined), clearPendingStart: vi.fn(async () => undefined),
  };
  return { store, read: () => saved };
}

export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
