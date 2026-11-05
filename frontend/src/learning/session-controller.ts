import { api as defaultApi, boundApi, ApiError, errorText, type LearningApi } from '../api/client';
import { scopedStorage, verifiedLegacySession, type LearningStorage } from '../storage/database';
import { identity } from '../storage/identity';
import { createRecord, hasDirtyDrafts, type SessionRecord, type SessionSnapshot } from './model';
import { SerialQueue } from './serial';
import { mergeSession } from './merge';
import { DraftSync } from './draft-sync';
import { SessionMutations } from './mutations';

export class SessionController {
  readonly queue = new SerialQueue();
  readonly sync = new DraftSync(this);
  readonly actions = new SessionMutations(this, this.sync);
  private readonly writes = new SerialQueue();
  private listeners = new Set<() => void>();
  private loadPromise: Promise<void> | null = null;
  private suspended = false;
  readonly api: LearningApi;
  private readonly store: LearningStorage;
  private readonly usesBrowserStore: boolean;
  private state: SessionSnapshot = {
    record: null, loading: true, busy: null, syncing: false, conflict: false,
    error: null, formError: null, storageError: null, accessDenied: false,
  };

  constructor(
    readonly id: string,
    client: LearningApi = defaultApi,
    store?: LearningStorage,
  ) {
    this.api = client === defaultApi ? boundApi(identity.current()) : client;
    this.store = store ?? scopedStorage(identity.current() ?? 'unverified');
    this.usesBrowserStore = !store;
  }

  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  patch(change: Partial<SessionSnapshot>) {
    if (this.suspended) return;
    this.state = { ...this.state, ...change };
    this.listeners.forEach((listener) => listener());
  }

  update(change: (record: SessionRecord) => SessionRecord): Promise<void> {
    if (this.suspended || !this.state.record) return Promise.resolve();
    const record = { ...change(this.state.record), saved_at: Math.max(Date.now(), this.state.record.saved_at + 1) };
    this.patch({ record });
    this.store.journal(record);
    return this.persist(record);
  }

  private persist(record: SessionRecord) {
    const snapshot = structuredClone(record);
    return this.writes.run(async () => {
      try {
        await this.store.saveSession(snapshot);
        this.patch({ storageError: null });
      } catch (error) {
        this.patch({ storageError: 'Браузер не сохранил данные. Не закрывайте эту вкладку. Освободите место или разрешите локальное хранилище.' });
        throw error;
      }
    });
  }

  load(): Promise<void> {
    this.loadPromise ??= this.loadInitial();
    return this.loadPromise;
  }

  private async loadInitial() {
    try {
      const record = await this.store.session(this.id);
      if (record) this.patch({ record, loading: false });
    } catch {
      this.patch({ storageError: 'Локальное хранилище недоступно. Восстановление черновика после закрытия не гарантируется.' });
    }
    await this.refresh();
  }

  async refresh() {
    if (this.suspended) return;
    await this.queue.run(async () => {
      try {
        const remote = await this.api.session(this.id);
        if (this.suspended) return;
        const local = this.state.record ?? (this.usesBrowserStore ? await verifiedLegacySession(this.id) : undefined);
        const conflict = Boolean(local && hasDirtyDrafts(local) && remote.draft_revision > local.session.draft_revision && remote.status === 'active');
        const record = local ? mergeSession(local, remote) : createRecord(remote);
        this.patch({
          record, loading: false, accessDenied: false, conflict: this.state.conflict || conflict,
          error: conflict ? 'На сервере есть более новый черновик. Локальный ввод восстановлен и не заменён. Подтвердите, какую версию отправить.' : null,
        });
        await this.persist(record);
        if (record.session.status === 'active') await this.store.setActive(this.id);
      } catch (error) {
        this.patch({
          loading: false,
          error: this.state.record ? `Показана сохранённая копия. ${errorText(error)}` : errorText(error),
          accessDenied: error instanceof ApiError && [401, 404].includes(error.status),
        });
      }
    });
    if (this.state.record && hasDirtyDrafts(this.state.record)) this.sync.schedule();
  }

  edit(answer: string) {
    const { record, busy, accessDenied } = this.state;
    if (!record || busy || accessDenied || record.pending_attempt || record.pending_finish || record.extension_key || record.session.status !== 'active') return;
    const id = record.session.tasks[record.current_index]?.id;
    if (!id) return;
    this.patch({ formError: null });
    void this.update((latest) => ({
      ...latest,
      drafts: { ...latest.drafts, [id]: { ...latest.drafts[id], answer, version: latest.drafts[id].version + 1 } },
    })).catch(() => undefined);
    this.sync.schedule();
  }

  recordTime(taskId: string, activeSeconds: number) {
    const record = this.state.record;
    const draft = record?.drafts[taskId];
    if (!record || !draft || record.session.status !== 'active' || activeSeconds <= draft.active_seconds) return;
    void this.update((latest) => ({
      ...latest,
      drafts: {
        ...latest.drafts,
        [taskId]: { ...latest.drafts[taskId], active_seconds: activeSeconds, version: latest.drafts[taskId].version + 1 },
      },
    })).catch(() => undefined);
    this.sync.schedule();
  }

  async goTo(index: number) {
    const { record, busy } = this.state;
    if (!record || busy || record.pending_attempt || record.pending_finish || record.extension_key || index < 0 || index >= record.session.tasks.length) return;
    const id = record.session.tasks[index].id;
    await this.update((latest) => ({
      ...latest,
      current_index: index,
      drafts: { ...latest.drafts, [id]: { ...latest.drafts[id], version: latest.drafts[id].version + 1 } },
    })).catch(() => undefined);
    this.patch({ formError: null });
    void this.sync.flush();
  }

  async retry() {
    if (this.suspended) return;
    if (this.state.accessDenied) {
      await this.refresh();
      if (this.state.accessDenied) return;
    }
    if (this.state.record?.pending_attempt) await this.actions.submit();
    else if (this.state.record?.pending_finish) await this.actions.finish();
    else if (this.state.record?.extension_key) await this.actions.extend();
    else {
      await this.sync.flush();
      if (!this.state.record) await this.refresh();
    }
  }

  async suspend() {
    this.sync.stop();
    this.suspended = true;
    this.state = { ...this.state, record: null, loading: false, busy: null, accessDenied: true };
    this.listeners.forEach((listener) => listener());
    await this.queue.run(async () => undefined);
    await this.writes.run(async () => undefined);
  }
}

const controllers = new Map<string, SessionController>();

export function sessionController(id: string) {
  const key = `${identity.current() ?? 'unverified'}:${id}`;
  let controller = controllers.get(key);
  if (!controller) {
    controller = new SessionController(id);
    controllers.set(key, controller);
  }
  return controller;
}

identity.beforeChange(async () => {
  const previous = [...controllers.values()];
  controllers.clear();
  await Promise.all(previous.map((controller) => controller.suspend()));
});

if (typeof window !== 'undefined') {
  window.addEventListener('online', () => {
    for (const controller of controllers.values()) void controller.retry();
  });
}
