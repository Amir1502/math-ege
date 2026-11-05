import { openDB, type DBSchema } from 'idb';
import type { Lesson } from '../api/types';
import type { PendingStart, SessionRecord } from '../learning/model';
import { identity, type IdentityView } from './identity';

interface LearningDatabase extends DBSchema {
  sessions: { key: string; value: SessionRecord };
  lessons: { key: number; value: { lesson: Lesson; saved_at: number } };
  meta: { key: string; value: string | PendingStart };
  scoped_sessions: { key: [string, string]; value: SessionRecord };
  scoped_meta: { key: [string, string]; value: string | PendingStart };
  revision_lessons: { key: string; value: { lesson: Lesson; saved_at: number } };
}

let database: ReturnType<typeof openDB<LearningDatabase>> | undefined;

function db() {
  database ??= openDB<LearningDatabase>('math-ege-learning-v1', 2, {
    upgrade(connection, oldVersion) {
      if (oldVersion < 1) {
        connection.createObjectStore('sessions');
        connection.createObjectStore('lessons');
        connection.createObjectStore('meta');
      }
      if (oldVersion < 2) {
        connection.createObjectStore('scoped_sessions');
        connection.createObjectStore('scoped_meta');
        connection.createObjectStore('revision_lessons');
      }
    },
    blocking() { void database?.then((connection) => connection.close()); },
  });
  return database;
}

type DraftJournal = Pick<SessionRecord, 'drafts' | 'current_index' | 'pending_attempt' | 'finish_key' | 'pending_finish' | 'extension_key' | 'extension_start' | 'saved_at'>;

function journalKey(owner: string, id: string) { return `math-ege:draft:v2:${owner}:${id}`; }

export function scopedStorage(owner: string) {
  return {
  async session(id: string): Promise<SessionRecord | undefined> {
    const record = await (await db()).get('scoped_sessions', [owner, id]);
    if (!record) return undefined;
    try {
      const raw = globalThis.localStorage?.getItem(journalKey(owner, id));
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
      const { drafts, current_index, pending_attempt, finish_key, pending_finish, extension_key, extension_start, saved_at } = record;
      globalThis.localStorage?.setItem(journalKey(owner, record.session.id), JSON.stringify({ drafts, current_index, pending_attempt, finish_key, pending_finish, extension_key, extension_start, saved_at }));
    } catch {
      // A full or disabled localStorage does not prevent durable IndexedDB writes.
    }
  },

  async saveSession(record: SessionRecord) {
    await (await db()).put('scoped_sessions', record, [owner, record.session.id]);
  },
  async setActive(id: string) { await (await db()).put('scoped_meta', id, [owner, 'active_session']); },
  async active() {
    const value = await (await db()).get('scoped_meta', [owner, 'active_session']);
    return typeof value === 'string' ? value : null;
  },
  async lesson(key: number | string, revision = 'unverified') { return (await db()).get('revision_lessons', `${revision}:${key}`); },
  async saveLesson(lesson: Lesson, revision = 'unverified', key: number | string = lesson.slot) {
    const transaction = (await db()).transaction(['revision_lessons', 'scoped_meta'], 'readwrite');
    await Promise.all([
      transaction.objectStore('revision_lessons').put({ lesson, saved_at: Date.now() }, `${revision}:${key}`),
      revision !== 'unverified' ? transaction.objectStore('scoped_meta').put(revision, ['public', 'lesson_catalog_revision']) : Promise.resolve(),
      transaction.done,
    ]);
  },
  async pendingStart() {
    const value = await (await db()).get('scoped_meta', [owner, 'pending_start']);
    return value && typeof value !== 'string' ? value : null;
  },
  async savePendingStart(value: PendingStart) { await (await db()).put('scoped_meta', value, [owner, 'pending_start']); },
  async clearPendingStart() { await (await db()).delete('scoped_meta', [owner, 'pending_start']); },
  };
}

export const storage: LearningStorage = {
  session: (id) => scopedStorage(identity.current() ?? 'unverified').session(id),
  journal: (record) => scopedStorage(identity.current() ?? 'unverified').journal(record),
  saveSession: (record) => scopedStorage(identity.current() ?? 'unverified').saveSession(record),
  setActive: (id) => scopedStorage(identity.current() ?? 'unverified').setActive(id),
  active: () => scopedStorage(identity.current() ?? 'unverified').active(),
  lesson: (slot, revision) => scopedStorage('public').lesson(slot, revision),
  saveLesson: (lesson, revision, key) => scopedStorage('public').saveLesson(lesson, revision, key),
  pendingStart: () => scopedStorage(identity.current() ?? 'unverified').pendingStart(),
  savePendingStart: (value) => scopedStorage(identity.current() ?? 'unverified').savePendingStart(value),
  clearPendingStart: () => scopedStorage(identity.current() ?? 'unverified').clearPendingStart(),
};

export type LearningStorage = ReturnType<typeof scopedStorage>;

/** Only for opened public lessons when the current catalog cannot be fetched. */
export async function cachedLessonRevision() {
  const value = await (await db()).get('scoped_meta', ['public', 'lesson_catalog_revision']);
  return typeof value === 'string' ? value : undefined;
}

export async function adoptIdentity(value: IdentityView) {
  const connection = await db();
  const target = scopedStorage(value.id);
  for (const owner of value.owner_ids) {
    if (owner === value.id) continue;
    const source = scopedStorage(owner);
    const keys = await connection.getAllKeys('scoped_sessions', IDBKeyRange.bound([owner, ''], [owner, '\uffff']));
    for (const [, id] of keys) {
      const record = await source.session(id);
      const existing = await target.session(id);
      if (record && (!existing || record.saved_at > existing.saved_at)) await target.saveSession(record);
    }
    const active = await source.active();
    if (active && !(await target.active())) await target.setActive(active);
    const pending = await source.pendingStart();
    if (pending && !(await target.pendingStart())) await target.savePendingStart(pending);
  }
}

export async function verifiedLegacySession(id: string): Promise<SessionRecord | undefined> {
  const record = await (await db()).get('sessions', id);
  if (!record) return undefined;
  try {
    const raw = globalThis.localStorage?.getItem(`math-ege:draft:${id}`);
    const journal = raw ? JSON.parse(raw) as DraftJournal : null;
    if (journal && journal.saved_at >= record.saved_at && record.session.status === 'active') return { ...record, ...journal };
  } catch { /* The original IndexedDB snapshot is preserved. */ }
  return record;
}
