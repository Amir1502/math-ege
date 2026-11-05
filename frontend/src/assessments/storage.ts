import { openDB, type DBSchema, type IDBPDatabase } from 'idb';
import type { AssessmentRecord, AssessmentStorage } from './model';
import type { Pending, PrepareBody } from './types';

interface AssessmentDatabase extends DBSchema {
  records: { key: string; value: AssessmentRecord };
  creates: { key: string; value: Pending<PrepareBody> | null };
  meta: { key: string; value: string };
}

const recordKey = (owner: string, id: string, device: string) => JSON.stringify([owner, id, device]);
const createKey = (owner: string, device: string) => JSON.stringify([owner, device]);
const journalKey = (key: string) => `math-ege:assessment:v1:${key}`;

/** Own database and owner/device-scoped synchronous journal; never stores credentials. */
export class AssessmentRepository implements AssessmentStorage {
  private database?: Promise<IDBPDatabase<AssessmentDatabase>>;

  constructor(
    private readonly name = 'math-ege-assessments-v1',
    private readonly synchronousStorage: Storage = globalThis.localStorage,
  ) {}

  private db() {
    this.database ??= openDB<AssessmentDatabase>(this.name, 1, {
      upgrade(connection) {
        connection.createObjectStore('records');
        connection.createObjectStore('creates');
        connection.createObjectStore('meta');
      },
      blocking: () => { void this.close(); },
    });
    return this.database;
  }

  async load(ownerId: string, id: string, deviceId: string): Promise<AssessmentRecord | undefined> {
    const key = recordKey(ownerId, id, deviceId);
    const stored = await (await this.db()).get('records', key);
    let journal: AssessmentRecord | undefined;
    try {
      const raw = this.synchronousStorage.getItem(journalKey(key));
      const candidate = raw ? JSON.parse(raw) as AssessmentRecord : null;
      if (candidate?.schema === 1 && candidate.owner_id === ownerId && candidate.device_id === deviceId
        && candidate.view.id === id && Number.isInteger(candidate.sequence)) journal = candidate;
    } catch { /* A valid durable database copy still permits recovery of public conditions. */ }
    return journal && (!stored || journal.sequence >= stored.sequence) ? journal : stored;
  }

  journal(record: AssessmentRecord) {
    this.synchronousStorage.setItem(journalKey(recordKey(record.owner_id, record.view.id, record.device_id)), JSON.stringify(record));
  }

  async save(record: AssessmentRecord) {
    const key = recordKey(record.owner_id, record.view.id, record.device_id);
    const transaction = (await this.db()).transaction('records', 'readwrite');
    const current = await transaction.store.get(key);
    if (!current || current.sequence <= record.sequence) await transaction.store.put(record, key);
    await transaction.done;
  }

  async pendingCreate(ownerId: string, deviceId: string): Promise<Pending<PrepareBody> | null> {
    const key = createKey(ownerId, deviceId);
    const raw = this.synchronousStorage.getItem(journalKey(`create:${key}`));
    if (raw) return JSON.parse(raw) as Pending<PrepareBody> | null;
    return (await (await this.db()).get('creates', key)) ?? null;
  }

  async savePendingCreate(ownerId: string, deviceId: string, pending: Pending<PrepareBody> | null) {
    const key = createKey(ownerId, deviceId);
    this.synchronousStorage.setItem(journalKey(`create:${key}`), JSON.stringify(pending));
    await (await this.db()).put('creates', pending, key);
  }

  async last(ownerId: string): Promise<string | null> {
    return (await (await this.db()).get('meta', JSON.stringify([ownerId, 'last']))) ?? null;
  }

  async setLast(ownerId: string, id: string) {
    await (await this.db()).put('meta', id, JSON.stringify([ownerId, 'last']));
  }

  async close() {
    const connection = await this.database;
    connection?.close();
    this.database = undefined;
  }
}
