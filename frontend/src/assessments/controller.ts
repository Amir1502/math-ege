import { ApiError } from '../api/client';
import { completeConditions } from './api';
import { answersFor, canEdit, canFreeze, createAssessmentRecord, hasLocalChanges } from './model';
import type { AssessmentRecord, AssessmentSnapshot, AssessmentStorage } from './model';
import type { AssessmentApi, AssessmentView, DraftBody } from './types';
import { browserClock, ServerClock, type AssessmentClockSource } from './clock';

const storageMessage = 'Не удалось сохранить вариант на устройстве. Освободите место или разрешите хранилище и повторите сохранение.';
const phases: AssessmentView['status'][] = ['prepared', 'active', 'awaiting_snapshot', 'completed'];

export class AssessmentController {
  private state: AssessmentSnapshot;
  private listeners = new Set<() => void>();
  private loadPromise?: Promise<void>;
  private refreshPromise?: Promise<void>;
  private flushPromise?: Promise<void>;
  private pendingDraft?: { body: DraftBody; version: number };
  private operationPromise?: Promise<void>;
  private retryPromise?: Promise<void>;
  private saveTail: Promise<void> = Promise.resolve();
  private saveTimer?: ReturnType<typeof setTimeout>;
  private flushTimer?: ReturnType<typeof setTimeout>;
  private blocked = false;
  private disposed = false;
  private readonly clock: ServerClock;
  private visible = false;
  private activeStamp = 0;

  constructor(
    readonly id: string,
    readonly ownerId: string,
    readonly deviceId: string,
    private readonly api: AssessmentApi,
    private readonly storage: AssessmentStorage,
    private readonly time: AssessmentClockSource = browserClock,
  ) {
    this.clock = new ServerClock(time);
    this.state = {
      record: null, loading: true, busy: null, syncing: false,
      online: globalThis.navigator?.onLine !== false, error: null, storageError: null,
      dirty: false, readOnly: true, remainingSeconds: null,
    };
  }

  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };

  private publish(patch: Partial<AssessmentSnapshot>) {
    this.state = { ...this.state, ...patch };
    this.state = {
      ...this.state,
      dirty: Boolean(this.state.record && hasLocalChanges(this.state.record)),
      remainingSeconds: this.state.record ? this.clock.remaining(this.state.record.view.deadline_at) : null,
      readOnly: this.disposed || !canEdit(this.state.record) || Boolean(this.state.storageError)
        || Boolean(this.state.record?.view.deadline_at && this.clock.remaining(this.state.record.view.deadline_at) === 0),
    };
    this.listeners.forEach((listener) => listener());
  }

  private commit(record: AssessmentRecord) {
    const next = { ...record, clock: this.clock.snapshot(), sequence: (this.state.record?.sequence ?? record.sequence) + 1 };
    try { this.storage.journal(next); }
    catch { this.publish({ storageError: storageMessage }); }
    this.publish({ record: next });
    if (!this.saveTimer && !this.disposed) this.saveTimer = setTimeout(() => {
      this.saveTimer = undefined;
      void this.persist().catch(() => undefined);
    }, 750);
  }

  async persist(record = this.state.record): Promise<void> {
    if (!record) return;
    const snapshot = structuredClone(record);
    const saving = this.saveTail.catch(() => undefined).then(async () => {
      try {
        // Do not overwrite the immediate journal with an older queued database write.
        this.storage.journal(this.state.record ?? snapshot);
        await this.storage.save(snapshot);
        this.publish({ storageError: null });
      } catch (error) {
        this.publish({ storageError: storageMessage });
        throw error;
      }
    });
    this.saveTail = saving;
    return saving;
  }

  load(): Promise<void> {
    this.loadPromise ??= this.loadOnce();
    return this.loadPromise;
  }

  private async loadOnce() {
    try {
      const cached = await this.storage.load(this.ownerId, this.id, this.deviceId);
      if (this.disposed) return;
      if (cached && cached.owner_id === this.ownerId && cached.device_id === this.deviceId && completeConditions(cached.view.tasks)) {
        this.clock.restore(cached.clock);
        this.publish({ record: cached, loading: false });
        this.tick();
      }
    } catch { this.publish({ storageError: storageMessage }); }
    if (this.state.online) {
      await this.refresh();
      void this.resumePending();
    }
    else this.publish({ loading: false });
  }

  refresh(): Promise<void> {
    if (this.disposed) return Promise.resolve();
    if (this.refreshPromise) return this.refreshPromise;
    this.refreshPromise = this.refreshOnce().finally(() => { this.refreshPromise = undefined; });
    return this.refreshPromise;
  }

  private async refreshOnce() {
    if (!this.state.online) { this.publish({ loading: false }); return; }
    try {
      const remote = await this.api.get(this.id, this.deviceId);
      if (this.disposed) return;
      this.adopt(remote);
      await this.persist();
      this.publish({ error: null });
    } catch (error) { await this.networkError(error, false); }
    finally { this.publish({ loading: false }); }
  }

  private adopt(remote: AssessmentView) {
    const local = this.state.record;
    if (local && (remote.writer_generation < local.view.writer_generation
      || remote.draft_revision < local.view.draft_revision
      || phases.indexOf(remote.status) < phases.indexOf(local.view.status))) return;
    this.clock.observe(remote.server_now);
    if (!local) {
      this.commit(createAssessmentRecord(remote, this.ownerId, this.deviceId));
      this.tick();
      return;
    }
    const keep = hasLocalChanges(local) || Boolean(local.frozen);
    const sent = this.pendingDraft;
    const observesDraft = sent && remote.writer_generation === sent.body.writer_generation
      && remote.draft_revision === sent.body.expected_revision + 1 && remote.current_index === sent.body.current_index
      && Object.entries(sent.body.answers).every(([id, answer]) => remote.drafts[id]?.answer === answer.answer
        && remote.drafts[id].active_seconds >= answer.active_seconds);
    const confirmedTakeover = Boolean(local.pending_takeover && remote.can_write
      && remote.writer_generation === local.pending_takeover.body.writer_generation + 1);
    let conflict = local.conflict === 'access' ? null : local.conflict;
    if (remote.status === 'completed') conflict = null;
    else if (confirmedTakeover) conflict = keep ? 'revision' : null;
    else if (!remote.can_write || remote.writer_generation !== local.view.writer_generation) conflict = 'writer';
    else if (hasLocalChanges(local) && remote.draft_revision !== local.view.draft_revision && !local.frozen && !observesDraft) conflict = 'revision';
    this.commit({
      ...local, view: remote, conflict,
      acknowledged_version: observesDraft ? Math.max(local.acknowledged_version, sent.version) : local.acknowledged_version,
      pending_activation: remote.status !== 'prepared' || (local.pending_activation
        && local.pending_activation.body.writer_generation !== remote.writer_generation) ? null : local.pending_activation,
      pending_takeover: remote.status === 'completed' || confirmedTakeover || (local.pending_takeover
        && local.pending_takeover.body.writer_generation !== remote.writer_generation) ? null : local.pending_takeover,
      drafts: keep ? local.drafts : answersFor(remote),
      current_index: keep ? local.current_index : remote.current_index,
    });
    this.tick();
  }

  edit(answer: string) {
    this.tick();
    const record = this.state.record;
    if (!record || this.state.readOnly || answer.length > 64) return;
    const task = record.view.tasks[record.current_index];
    if (record.drafts[task.id].answer === answer) return;
    this.commit({ ...record, local_version: record.local_version + 1,
      drafts: { ...record.drafts, [task.id]: { ...record.drafts[task.id], answer } } });
    this.scheduleFlush();
  }

  goTo(index: number) {
    if (this.disposed) return;
    this.tick();
    const record = this.state.record;
    if (!record || !Number.isInteger(index) || index < 0 || index >= record.view.tasks.length) return;
    this.commit({ ...record, current_index: index, local_version: record.local_version + (canEdit(record) ? 1 : 0) });
    void this.flush();
  }

  private scheduleFlush() {
    // Throttle from the first dirty change; continuous typing cannot postpone a write.
    if (!this.flushTimer && !this.blocked && !this.disposed) this.flushTimer = setTimeout(() => {
      this.flushTimer = undefined;
      void this.flush();
    }, 1200);
  }

  flush(): Promise<void> {
    if (this.flushPromise) return this.flushPromise;
    if (this.flushTimer) clearTimeout(this.flushTimer);
    this.flushTimer = undefined;
    this.flushPromise = this.flushLoop().finally(() => { this.flushPromise = undefined; this.publish({ syncing: false }); });
    return this.flushPromise;
  }

  private async flushLoop() {
    while (!this.disposed && this.state.online && !this.blocked) {
      const record = this.state.record;
      if (!record || !canEdit(record) || !hasLocalChanges(record)) return;
      const version = record.local_version;
      const body: DraftBody = {
        device_id: this.deviceId, writer_generation: record.view.writer_generation,
        expected_revision: record.view.draft_revision, current_index: record.current_index,
        answers: structuredClone(record.drafts),
      };
      this.publish({ syncing: true });
      try {
        await this.persist(record);
        this.tick();
        const ready = this.state.record;
        if (this.disposed || !this.state.online || this.blocked || !canEdit(ready)
          || ready?.view.writer_generation !== body.writer_generation || ready.view.draft_revision !== body.expected_revision) return;
        this.pendingDraft = { body, version };
        const reply = await this.api.draft(this.id, body);
        if (this.disposed) return;
        const current = this.state.record!;
        if (current.view.writer_generation !== body.writer_generation) return;
        this.commit({ ...current,
          view: { ...current.view, draft_revision: Math.max(current.view.draft_revision, reply.draft_revision),
            ...(current.view.status === 'active' && reply.draft_revision >= current.view.draft_revision
              ? { drafts: body.answers, current_index: body.current_index } : {}),
          },
          acknowledged_version: Math.max(current.acknowledged_version, version),
        });
        this.publish({ error: null });
      } catch (error) { await this.networkError(error); return; }
      finally { this.pendingDraft = undefined; }
    }
  }

  setOnline(online: boolean) {
    if (this.disposed) return;
    const changed = this.state.online !== online;
    this.publish({ online });
    const record = this.state.record;
    if (!online && record?.view.status === 'active' && !record.connection_lost) {
      this.commit({ ...record, connection_lost: true });
    }
    // One attempt per actual reconnect, never a polling loop.
    if (changed && online && record) void this.retry();
  }

  retry(): Promise<void> {
    if (this.retryPromise) return this.retryPromise;
    this.retryPromise = this.retryOnce().finally(() => { this.retryPromise = undefined; });
    return this.retryPromise;
  }

  private async retryOnce() {
    if (this.disposed) return;
    try { await this.persist(); }
    catch { return; }
    if (!this.state.online || this.disposed) return;
    this.blocked = false;
    await this.refresh();
    await this.resumePending();
  }

  private async resumePending() {
    if (this.disposed || this.blocked) return;
    if (this.state.record?.pending_takeover && this.state.record.conflict !== 'access') {
      await this.takeover();
      return;
    }
    if (this.state.record?.conflict) return;
    if (this.state.record?.frozen) await this.finish();
    else if (this.state.record?.pending_activation) await this.activate();
    else await this.flush();
  }

  setVisible(visible: boolean) {
    if (this.disposed) return;
    this.tick();
    this.visible = visible;
    this.activeStamp = this.time.monotonicNow();
  }

  tick() { this.updateClock(true); }

  private updateClock(autoFinish: boolean) {
    const record = this.state.record;
    if (!record || this.disposed) return;
    const monotonic = this.time.monotonicNow();
    const seconds = this.visible && canEdit(record)
      ? Math.min(Math.max(0, Math.floor((monotonic - this.activeStamp) / 1000)), this.state.remainingSeconds ?? 86_400)
      : 0;
    if (seconds > 0) {
      this.activeStamp += seconds * 1000;
      const task = record.view.tasks[record.current_index];
      this.commit({ ...record, local_version: record.local_version + 1,
        drafts: { ...record.drafts, [task.id]: { ...record.drafts[task.id], active_seconds: Math.min(86_400, record.drafts[task.id].active_seconds + seconds) } },
      });
      this.scheduleFlush();
    } else if (!this.visible) this.activeStamp = monotonic;
    if (record.view.status === 'active' && !record.frozen) this.commit(this.state.record!);
    else this.publish({});
    if (autoFinish && (this.state.remainingSeconds === 0 || record.view.status === 'awaiting_snapshot') && canFreeze(this.state.record)) void this.finish();
  }

  async resolveConflict(choice: 'local' | 'server') {
    if (this.disposed || !this.state.online || this.state.busy) return;
    try {
      const remote = await this.api.get(this.id, this.deviceId);
      if (this.disposed) return;
      const record = this.state.record;
      if (!record) return;
      if (record.frozen) {
        if (choice !== 'local') return;
        if (!remote.can_write || remote.writer_generation !== record.frozen.body.writer_generation) { this.adopt(remote); return; }
        this.commit({ ...record, view: remote, conflict: null });
        this.blocked = false;
        await this.finish();
        return;
      }
      if (!remote.can_write || remote.status !== 'active') { this.adopt(remote); return; }
      this.blocked = false;
      const version = record.local_version + 1;
      this.commit({ ...record, view: remote, conflict: null,
        drafts: choice === 'local' ? record.drafts : answersFor(remote),
        current_index: choice === 'local' ? record.current_index : remote.current_index,
        local_version: version, acknowledged_version: choice === 'server' ? version : record.acknowledged_version,
      });
      this.publish({ error: null });
      await this.persist();
      if (choice === 'local') await this.flush();
    } catch (error) { await this.networkError(error); }
  }

  activate(): Promise<void> {
    const record = this.state.record;
    if (this.disposed || !record || record.view.status !== 'prepared' || !record.view.can_write
      || record.conflict || !this.state.online || !completeConditions(record.view.tasks)) return Promise.resolve();
    if (!record.pending_activation) this.commit({ ...record, pending_activation: {
      key: crypto.randomUUID(), body: { device_id: this.deviceId, writer_generation: record.view.writer_generation },
    } });
    return this.operation('activate', async () => {
      await this.persist();
      const current = this.state.record;
      const pending = current?.pending_activation;
      if (this.disposed || !this.state.online || !current || !pending || current.conflict
        || !current.view.can_write || current.view.status !== 'prepared'
        || current.view.writer_generation !== pending.body.writer_generation) return;
      const remote = await this.api.activate(this.id, pending.body, pending.key);
      if (this.disposed) return;
      this.blocked = false;
      this.adopt(remote);
      await this.persist();
    });
  }

  /** Called only after the UI's explicit takeover confirmation. */
  takeover(): Promise<void> {
    const record = this.state.record;
    if (this.disposed || !record || record.frozen || record.view.status === 'completed' || !this.state.online) return Promise.resolve();
    if (!record.pending_takeover) this.commit({ ...record, pending_takeover: {
      key: crypto.randomUUID(), body: { device_id: this.deviceId, writer_generation: record.view.writer_generation },
    } });
    return this.operation('takeover', async () => {
      await this.persist();
      const current = this.state.record;
      const pending = current?.pending_takeover;
      if (this.disposed || !this.state.online || !current || !pending || current.conflict === 'access'
        || current.frozen || current.view.status === 'completed'
        || current.view.writer_generation !== pending.body.writer_generation) return;
      const remote = await this.api.takeover(this.id, pending.body, pending.key);
      if (this.disposed) return;
      this.blocked = false;
      this.adopt(remote);
      await this.persist();
    });
  }

  finish(): Promise<void> {
    if (this.disposed) return Promise.resolve();
    this.updateClock(false);
    const record = this.state.record;
    if (!record || record.view.status === 'completed') return Promise.resolve();
    if (!record.frozen) {
      if (!canFreeze(record)) return Promise.resolve();
      this.commit({ ...record, frozen: {
        key: crypto.randomUUID(),
        body: { device_id: this.deviceId, writer_generation: record.view.writer_generation,
          answers: structuredClone(record.drafts), connection_lost: record.connection_lost || !this.state.online || record.view.status === 'awaiting_snapshot' },
      } });
    }
    return this.operation('finish', async () => {
      await this.persist();
      if (this.disposed || !this.state.online || this.state.record?.conflict) return;
      await this.flushPromise;
      const current = this.state.record;
      if (this.disposed || !this.state.online || !current?.frozen || current.conflict
        || !current.view.can_write || current.view.status === 'completed'
        || current.view.writer_generation !== current.frozen.body.writer_generation) return;
      const frozen = current.frozen;
      const remote = await this.api.finish(this.id, frozen.body, frozen.key);
      if (this.disposed) return;
      this.adopt(remote);
      await this.persist();
    });
  }

  private operation(kind: AssessmentSnapshot['busy'], run: () => Promise<void>): Promise<void> {
    if (this.disposed) return Promise.resolve();
    if (this.operationPromise) {
      return this.state.busy === kind ? this.operationPromise : this.operationPromise.then(() => this.operation(kind, run));
    }
    this.publish({ busy: kind, error: null });
    this.operationPromise = Promise.resolve().then(run).catch((error: unknown) => {
      return this.networkError(error);
    }).finally(() => {
      this.operationPromise = undefined;
      this.publish({ busy: null });
    });
    return this.operationPromise;
  }

  private async networkError(error: unknown, reconcile = true) {
    if (this.disposed) return;
    this.blocked = true;
    const record = this.state.record;
    if (error instanceof ApiError && record) {
      if (error.status === 401 || error.status === 403 || error.status === 404 || error.code === 'identity_changed') {
        this.commit({ ...record, conflict: 'access' });
      } else if (error.code === 'assessment_draft_conflict') {
        this.commit({ ...record, conflict: 'revision' });
      } else if (error.code === 'assessment_writer_conflict') {
        this.commit({ ...record, conflict: 'writer' });
      } else if (error.retryable && !record.connection_lost) {
        this.commit({ ...record, connection_lost: true });
      }
    }
    const message = error instanceof ApiError ? error.message : storageMessage;
    this.publish({ error: message });
    if (reconcile && error instanceof ApiError && ['assessment_not_active', 'assessment_closed', 'assessment_snapshot_conflict'].includes(error.code)) {
      await this.refresh();
    }
  }

  async suspend() {
    this.updateClock(false);
    this.dispose();
    await this.persist();
  }

  dispose() {
    this.disposed = true;
    if (this.saveTimer) clearTimeout(this.saveTimer);
    if (this.flushTimer) clearTimeout(this.flushTimer);
    this.publish({});
    this.listeners.clear();
  }
}
