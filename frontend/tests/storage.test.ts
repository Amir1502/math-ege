import { describe, expect, it } from 'vitest';
import { storage } from '../src/storage/database';
import { createRecord } from '../src/learning/model';
import { sessionFixture } from './fixtures';

describe('IndexedDB session records', () => {
  it('persists public conditions, raw drafts, position, active time, and an immutable pending request', async () => {
    const record = createRecord(sessionFixture());
    record.current_index = 1;
    record.drafts['task-2'] = { answer: '−0002,50', active_seconds: 14, version: 1, synced_version: 0 };
    record.pending_attempt = { key: crypto.randomUUID(), body: { task_id: 'task-2', answer: '−0002,50', active_seconds: 14, skipped: false } };
    await storage.saveSession(record);
    await storage.setActive(record.session.id);
    expect(await storage.active()).toBe(record.session.id);
    expect(await storage.session(record.session.id)).toEqual(record);
    expect(record.session.tasks[0]).not.toHaveProperty('answer');
  });
});
