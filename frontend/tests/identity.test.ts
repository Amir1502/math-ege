import { describe, expect, it, vi } from 'vitest';
import { IdentityManager, type IdentityView } from '../src/storage/identity';
import { adoptIdentity, scopedStorage } from '../src/storage/database';
import { createRecord } from '../src/learning/model';
import { deferred, sessionFixture } from './fixtures';

const actor = (id: string, owners = [id]): IdentityView => ({ id, kind: 'guest', owner_ids: owners });

describe('identity transitions', () => {
  it('quiesces the old identity before changing its cookie and publishing the next one', async () => {
    const order: string[] = [];
    let remote = actor('guest-a');
    const manager = new IdentityManager(async () => remote);
    await manager.refresh();
    manager.beforeChange(async () => { order.push('quiesced'); });
    await manager.transition(async () => {
      expect(manager.getSnapshot().changing).toBe(true);
      order.push('login');
      remote = { ...actor('account-b', ['account-b', 'guest-a']), kind: 'account' };
    });
    expect(order).toEqual(['quiesced', 'login']);
    expect(manager.current()).toBe('account-b');
    expect(manager.getSnapshot().changing).toBe(false);
  });

  it('never restores a previous identity after an ambiguous failed login and failed refresh', async () => {
    const resolver = vi.fn(async () => actor('guest-a'));
    const manager = new IdentityManager(resolver);
    await manager.refresh();
    resolver.mockRejectedValue(new Error('offline'));
    await expect(manager.transition(async () => { throw new Error('lost response'); })).rejects.toThrow('lost response');
    expect(manager.current()).toBeNull();
    expect(manager.getSnapshot().error).toBeTruthy();
  });

  it('does not publish the new identity while a durable old write is still running', async () => {
    const resolver = vi.fn(async () => actor('guest-a'));
    const manager = new IdentityManager(resolver);
    await manager.refresh();
    const write = deferred<void>();
    manager.beforeChange(() => write.promise);
    resolver.mockResolvedValue(actor('account-b'));
    const changed = manager.refresh();
    await Promise.resolve();
    expect(manager.getSnapshot().changing).toBe(true);
    expect(manager.current()).toBe('guest-a');
    write.resolve();
    await changed;
    expect(manager.current()).toBe('account-b');
  });
});

describe('identity-scoped durable records', () => {
  it('isolates sessions, active pointers, and queued UUIDs while preserving both histories', async () => {
    const first = scopedStorage('scope-a');
    const second = scopedStorage('scope-b');
    const record = createRecord(sessionFixture());
    const pending = { key: crypto.randomUUID(), body: { slots: [1], length: 5 as const, mode: 'practice' as const } };
    await first.saveSession(record);
    await first.setActive(record.session.id);
    await first.savePendingStart(pending);
    expect(await second.session(record.session.id)).toBeUndefined();
    expect(await second.active()).toBeNull();
    expect(await second.pendingStart()).toBeNull();
    expect(await first.session(record.session.id)).toEqual(record);
    expect(await first.pendingStart()).toEqual(pending);
  });

  it('adopts only server-verified guest origins and keeps the exact pending attempt', async () => {
    const guest = scopedStorage('claimed-guest');
    const other = scopedStorage('unrelated-guest');
    const record = createRecord(sessionFixture());
    record.pending_attempt = { key: crypto.randomUUID(), body: { task_id: 'task-1', answer: '2,50', active_seconds: 9, skipped: false } };
    await guest.saveSession(record);
    await guest.setActive(record.session.id);
    await other.saveSession({ ...record, session: { ...record.session, id: 'foreign-session' } });
    await adoptIdentity({ ...actor('linked-account', ['linked-account', 'claimed-guest']), kind: 'account' });
    const account = scopedStorage('linked-account');
    expect((await account.session(record.session.id))?.pending_attempt).toEqual(record.pending_attempt);
    expect(await account.session('foreign-session')).toBeUndefined();
    expect(await guest.session(record.session.id)).toEqual(record);
    expect(await account.active()).toBe(record.session.id);
  });
});
