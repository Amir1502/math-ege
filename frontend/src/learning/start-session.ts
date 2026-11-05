import { api } from '../api/client';
import type { StartBody } from '../api/types';
import { storage } from '../storage/database';
import { createRecord } from './model';

let inFlight: Promise<string> | null = null;

/** Guest creation is deliberately limited to this explicit start action. */
export function startSession(body: StartBody): Promise<string> {
  if (inFlight) return inFlight;
  inFlight = (async () => {
    let pending = await storage.pendingStart();
    if (!pending) {
      pending = { key: crypto.randomUUID(), body };
      await storage.savePendingStart(pending);
    }
    await api.guest();
    const session = await api.start(pending.body, pending.key);
    await storage.saveSession(createRecord(session));
    await storage.setActive(session.id);
    await storage.clearPendingStart();
    return session.id;
  })().finally(() => { inFlight = null; });
  return inFlight;
}
