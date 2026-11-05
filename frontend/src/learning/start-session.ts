import { api } from '../api/client';
import type { StartBody } from '../api/types';
import { scopedStorage } from '../storage/database';
import { identity } from '../storage/identity';
import { createRecord } from './model';

let inFlight: Promise<string> | null = null;

/** Guest creation is deliberately limited to this explicit start action. */
export function startSession(body: StartBody): Promise<string> {
  if (inFlight) return inFlight;
  inFlight = (async () => {
    if (identity.getSnapshot().changing) throw new Error('Дождитесь смены доступа.');
    await api.guest();
    const owner = await identity.refresh();
    if (!owner) throw new Error('Не удалось подтвердить доступ. Повторите начало занятия.');
    const storage = scopedStorage(owner.id);
    let pending = await storage.pendingStart();
    if (!pending) {
      pending = { key: crypto.randomUUID(), body };
      await storage.savePendingStart(pending);
    }
    if (identity.current() !== owner.id || identity.getSnapshot().changing) throw new Error('Доступ изменился. Начните занятие снова.');
    const session = await api.start(pending.body, pending.key);
    await storage.saveSession(createRecord(session));
    await storage.setActive(session.id);
    await storage.clearPendingStart();
    return session.id;
  })().finally(() => { inFlight = null; });
  return inFlight;
}
