import { openDB } from 'idb';
import type { DBSchema, IDBPDatabase, IDBPTransaction } from 'idb';
import { OfflineError } from './types';
import type { LearningSession, OfflineTask } from './types';
import { UUID, uuid } from './core/model';

export const DATABASE = 'math-ege-offline-v1';
const stores = ['meta', 'sessions', 'operations', 'exposures'] as const;
export type Device = { schema: 1; origin: 'device'; owner: string; created_at: string; active_session_id: string | null };
export type SessionRecord = {
  id: string; owner: string; origin: 'device'; schema: 1; course_revision: string;
  session: LearningSession; materials: OfflineTask[]; familiar_task_ids: string[];
};
export type Exposure = { owner: string; instance_key: string; last_seen: number;
  assistance_seen?: boolean; reference_seen?: boolean; numeric_attempted?: boolean };
export interface OfflineDatabase extends DBSchema {
  meta: { key: string; value: Device };
  sessions: { key: string; value: SessionRecord };
  operations: { key: string; value: { owner: string; payload: string; result: unknown } };
  exposures: { key: string; value: Exposure };
}
export type WriteTransaction = IDBPTransaction<OfflineDatabase, typeof stores, 'readwrite'>;
type ReadTransaction = IDBPTransaction<OfflineDatabase, typeof stores, 'readonly'>;

function deviceRecord(value: Device | undefined): Device {
  if (!value || value.schema !== 1 || value.origin !== 'device' || !UUID.test(value.owner)
    || !Number.isFinite(Date.parse(value.created_at))
    || (value.active_session_id !== null && !UUID.test(value.active_session_id))) {
    throw new OfflineError('storage_corrupt', 'Локальное хранилище не прошло проверку. История не изменялась; очистка данных не требуется.');
  }
  return value;
}

function storageError(error: unknown): never {
  if (error instanceof OfflineError) throw error;
  throw new OfflineError('storage_unavailable', 'Не удалось прочитать или сохранить данные на устройстве. Проверьте свободное место и повторите действие без очистки истории.');
}

export class OfflineRepository {
  private connection: Promise<IDBPDatabase<OfflineDatabase>> | null = null;

  private open(): Promise<IDBPDatabase<OfflineDatabase>> {
    if (!this.connection) {
      this.connection = new Promise<IDBPDatabase<OfflineDatabase>>((resolve, reject) => {
        let abandoned = false;
        void openDB<OfflineDatabase>(DATABASE, 1, {
          upgrade(db) { for (const name of stores) db.createObjectStore(name); },
          blocked() {
            abandoned = true;
            reject(new OfflineError('storage_blocked', 'Обновление хранилища заблокировано другим окном. Закройте второе окно приложения и повторите чтение.'));
          },
          blocking: (_current, _next, event) => { (event.target as IDBDatabase).close(); this.connection = null; },
          terminated: () => { this.connection = null; },
        }).then(async (db) => {
          if (abandoned) { db.close(); return; }
          try {
            const tx = db.transaction(stores, 'readwrite', { durability: 'strict' });
            const completed = tx.done.catch(() => undefined);
            try {
              const meta = tx.objectStore('meta');
              const existing = await meta.get('device');
              if (existing) deviceRecord(existing);
              else {
                if (await tx.objectStore('sessions').count() || await tx.objectStore('operations').count()
                  || await tx.objectStore('exposures').count()) {
                  throw new OfflineError('storage_corrupt', 'В истории отсутствует владелец. Данные не удалялись и не присваивались новому профилю.');
                }
                await meta.add({ schema: 1, origin: 'device', owner: uuid(),
                  created_at: new Date(Date.now()).toISOString(), active_session_id: null }, 'device');
              }
              await tx.done;
            } catch (error) {
              try { tx.abort(); } catch { /* An aborted transaction may already be closed. */ }
              await completed;
              throw error;
            }
            resolve(db);
          } catch (error) { db.close(); reject(error); }
        }, reject);
      }).catch((error: unknown) => { this.connection = null; return storageError(error); });
    }
    return this.connection;
  }

  async read<T>(action: (tx: ReadTransaction, device: Device) => Promise<T>): Promise<T> {
    try {
      const db = await this.open();
      const tx = db.transaction(stores, 'readonly');
      const completed = tx.done.catch(() => undefined);
      try {
        const result = await action(tx, deviceRecord(await tx.objectStore('meta').get('device')));
        await tx.done;
        return result;
      } catch (error) { await completed; throw error; }
    } catch (error) { return storageError(error); }
  }

  async write<T>(action: (tx: WriteTransaction, device: Device) => Promise<T>): Promise<T> {
    try {
      const db = await this.open();
      const tx = db.transaction(stores, 'readwrite', { durability: 'strict' });
      const completed = tx.done.catch(() => undefined);
      try {
        const result = await action(tx, deviceRecord(await tx.objectStore('meta').get('device')));
        await tx.done;
        return result;
      } catch (error) {
        try { tx.abort(); } catch { /* Keep the original domain error after an automatic abort. */ }
        await completed;
        throw error;
      }
    } catch (error) { return storageError(error); }
  }

  async close(): Promise<void> {
    const connection = this.connection;
    this.connection = null;
    if (connection) (await connection).close();
  }
}
