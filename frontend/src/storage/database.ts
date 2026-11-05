import { openDB, type DBSchema } from 'idb';
import type { Lesson } from '../api/types';
import type { PendingStart, SessionRecord } from '../learning/model';

interface LearningDatabase extends DBSchema {
  sessions: { key: string; value: SessionRecord };
  lessons: { key: number; value: { lesson: Lesson; saved_at: number } };
  meta: { key: string; value: string | PendingStart };
}

let database: ReturnType<typeof openDB<LearningDatabase>> | undefined;

function db() {
  database ??= openDB<LearningDatabase>('math-ege-learning-v1', 1, {
    upgrade(connection) {
      connection.createObjectStore('sessions');
      connection.createObjectStore('lessons');
      connection.createObjectStore('meta');
    },
    blocking() { void database?.then((connection) => connection.close()); },
  });
  return database;
}

type DraftJournal = Pick<SessionRecord, 'drafts' | 'current_index' | 'pending_attempt' | 'finish_key' | 'pending_finish' | 'saved_at'>;

function journalKey(id: string) { return `math-ege:draft:${id}`; }

export const storage = {
  async session(id: string): Promise<SessionRecord | undefined> {
    const record = await (await db()).get('sessions', id);
    if (!record) return undefined;
    try {
      const raw = globalThis.localStorage?.getItem(journalKey(id));
      const journal = raw ? JSON.parse(raw) as DraftJournal : null;
      if (journal && journal.saved_at >= record.saved_at && record.session.status === 'active') {
        return { ...record, ...journal };
      }
    } catch {
      // IndexedDB remains authoritative if the small synchronous unload journal is unavailable.
    }
    return record;
  },

  journal(record: SessionRecord) {
    try {
      const { drafts, current_index, pending_attempt, finish_key, pending_finish, saved_at } = record;
      globalThis.localStorage?.setItem(journalKey(record.session.id), JSON.stringify({ drafts, current_index, pending_attempt, finish_key, pending_finish, saved_at }));
    } catch {
      // A full or disabled localStorage does not prevent durable IndexedDB writes.
    }
  },

  async saveSession(record: SessionRecord) {
    await (await db()).put('sessions', record, record.session.id);
  },
  async setActive(id: string) { await (await db()).put('meta', id, 'active_session'); },
  async active() {
    const value = await (await db()).get('meta', 'active_session');
    return typeof value === 'string' ? value : null;
  },
  async lesson(slot: number) { return (await db()).get('lessons', slot); },
  async saveLesson(lesson: Lesson) {
    await (await db()).put('lessons', { lesson, saved_at: Date.now() }, lesson.slot);
  },
  async pendingStart() {
    const value = await (await db()).get('meta', 'pending_start');
    return value && typeof value !== 'string' ? value : null;
  },
  async savePendingStart(value: PendingStart) { await (await db()).put('meta', value, 'pending_start'); },
  async clearPendingStart() { await (await db()).delete('meta', 'pending_start'); },
};

export type LearningStorage = typeof storage;
