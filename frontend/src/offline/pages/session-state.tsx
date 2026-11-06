import type { OfflineRuntime } from '../practice';
import type { AttemptInput, DraftInput, Failure, Session } from './shared';
import { acknowledgeOperation, failure, isAnswerFormatFailure, operationKey, readOperation, writeOperation } from './operations';
import type { PendingOperation } from './operations';

type Draft = { answer: string; active_seconds: number };
type Busy = 'attempt' | 'hint' | 'solution' | 'finish' | 'position' | null;
export type WorksheetState = {
  session: Session;
  drafts: Record<string, Draft>;
  saving: 'saved' | 'dirty' | 'saving' | 'error';
  busy: Busy;
  error: Failure | null;
  queueError: Failure | null;
  formError: Failure | null;
  pendingAttempt: PendingOperation<AttemptInput> | null;
  pendingFinish: PendingOperation<{ session_id: string }> | null;
};

function pendingOperations(session: Session) {
  const pendingAttempt = readOperation<AttemptInput>('attempt', session.id);
  const pendingFinish = readOperation<{ session_id: string }>('finish', session.id);
  const body = pendingAttempt?.body;
  if ((pendingAttempt && (!body || typeof body !== 'object'
      || !session.tasks.some((task) => task.id === body.task_id) || typeof body.answer !== 'string'
      || !Number.isSafeInteger(body.active_seconds) || body.active_seconds < 0 || body.active_seconds > 86_400
      || typeof body.skipped !== 'boolean'))
    || (pendingFinish && (!pendingFinish.body || pendingFinish.body.session_id !== session.id))
    || (pendingAttempt && pendingFinish)) {
    throw { code: 'ui_queue_invalid', message: 'Сохранённая операция не соответствует этому занятию. Исходный ключ и история не изменялись.' } satisfies Failure;
  }
  return { pendingAttempt, pendingFinish };
}

export class WorksheetController {
  private snapshot: WorksheetState;
  private readonly listeners = new Set<() => void>();
  private readonly dirty = new Set<string>();
  private serial: Promise<void> = Promise.resolve();
  private saveTimer: ReturnType<typeof setTimeout> | null = null;
  private clockTimer: ReturnType<typeof setInterval> | null = null;
  private clockStarted: number | null = null;
  private readonly elapsed = new Map<string, number>();
  private mounted = false;

  constructor(private readonly runtime: OfflineRuntime, session: Session) {
    const drafts = Object.fromEntries(session.tasks.map((task) => [task.id, { ...(session.drafts[task.id] ?? { answer: '', active_seconds: 0 }) }]));
    let pendingAttempt: PendingOperation<AttemptInput> | null = null;
    let pendingFinish: PendingOperation<{ session_id: string }> | null = null;
    let error: Failure | null = null;
    try {
      ({ pendingAttempt, pendingFinish } = pendingOperations(session));
    } catch (caught) {
      error = failure(caught);
    }
    for (const task of session.tasks) this.elapsed.set(task.id, drafts[task.id].active_seconds * 1000);
    this.snapshot = { session, drafts, saving: 'saved', busy: null, error, queueError: error, formError: null, pendingAttempt, pendingFinish };
  }

  state = () => this.snapshot;

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  private publish(patch: Partial<WorksheetState> = {}) {
    this.snapshot = { ...this.snapshot, ...patch };
    for (const listener of this.listeners) listener();
  }

  private enqueue<T>(action: () => Promise<T>): Promise<T> {
    const next = this.serial.then(action, action);
    this.serial = next.then(() => undefined, () => undefined);
    return next;
  }

  private currentTaskId() {
    return this.snapshot.session.tasks[this.snapshot.session.current_index]?.id ?? null;
  }

  private checkpoint() {
    const id = this.currentTaskId();
    const now = performance.now();
    if (id && this.clockStarted !== null) {
      const milliseconds = (this.elapsed.get(id) ?? 0) + Math.max(0, now - this.clockStarted);
      this.elapsed.set(id, milliseconds);
      const active_seconds = Math.floor(milliseconds / 1000);
      const current = this.snapshot.drafts[id];
      if (current && current.active_seconds !== active_seconds && this.snapshot.session.status === 'active') {
        this.dirty.add(id);
        this.snapshot = { ...this.snapshot, drafts: { ...this.snapshot.drafts, [id]: { ...current, active_seconds } } };
      }
    }
    this.clockStarted = this.mounted && document.visibilityState === 'visible'
      && this.snapshot.session.status === 'active' && !this.snapshot.pendingFinish ? now : null;
  }

  private scheduleSave() {
    if (this.saveTimer !== null || this.dirty.size === 0 || !this.mounted) return;
    // Do not restart this timer on each keypress. Continuous typing must also
    // reach durable storage within one second of its first unsaved change.
    this.saveTimer = setTimeout(() => {
      this.saveTimer = null;
      void this.flush().catch(() => undefined);
    }, 500);
  }

  private visibilityChanged = () => {
    this.checkpoint();
    if (document.visibilityState === 'hidden') void this.flush().catch(() => undefined);
    else this.scheduleSave();
  };

  private pageHidden = () => {
    this.checkpoint();
    this.clockStarted = null;
    void this.flush().catch(() => undefined);
  };

  private beforeUnload = (event: BeforeUnloadEvent) => {
    if (this.dirty.size > 0 || this.snapshot.saving === 'saving' || this.snapshot.saving === 'error') {
      this.checkpoint();
      void this.flush().catch(() => undefined);
      event.preventDefault();
      event.returnValue = '';
    }
  };

  attach() {
    this.mounted = true;
    this.checkpoint();
    document.addEventListener('visibilitychange', this.visibilityChanged);
    window.addEventListener('pagehide', this.pageHidden);
    window.addEventListener('beforeunload', this.beforeUnload);
    this.clockTimer = setInterval(() => {
      this.checkpoint();
      if (this.dirty.size > 0) this.scheduleSave();
    }, 1000);
    return () => {
      this.checkpoint();
      this.mounted = false;
      this.clockStarted = null;
      document.removeEventListener('visibilitychange', this.visibilityChanged);
      window.removeEventListener('pagehide', this.pageHidden);
      window.removeEventListener('beforeunload', this.beforeUnload);
      if (this.clockTimer !== null) clearInterval(this.clockTimer);
      if (this.saveTimer !== null) clearTimeout(this.saveTimer);
      this.clockTimer = null;
      this.saveTimer = null;
      void this.flush().catch(() => undefined);
    };
  }

  edit(answer: string) {
    if (this.snapshot.busy || this.snapshot.queueError || this.snapshot.pendingAttempt || this.snapshot.pendingFinish || this.snapshot.session.status !== 'active') return;
    const id = this.currentTaskId();
    if (!id) return;
    this.checkpoint();
    this.dirty.add(id);
    this.publish({ drafts: { ...this.snapshot.drafts, [id]: { ...this.snapshot.drafts[id], answer } }, saving: 'dirty', formError: null });
    this.scheduleSave();
  }

  private async saveDrafts() {
    if (this.snapshot.session.status !== 'active') return;
    this.checkpoint();
    if (this.dirty.size === 0) return;
    this.publish({ saving: 'saving' });
    try {
      for (const id of Array.from(this.dirty)) {
        const draft = { ...this.snapshot.drafts[id] };
        const body: DraftInput = { task_id: id, ...draft, expected_revision: this.snapshot.session.draft_revision };
        const saved = await this.runtime.draft(this.snapshot.session.id, body);
        const local = this.snapshot.drafts[id];
        if (local.answer === draft.answer && local.active_seconds === draft.active_seconds) this.dirty.delete(id);
        this.snapshot = {
          ...this.snapshot,
          session: { ...this.snapshot.session, draft_revision: saved.draft_revision, drafts: { ...this.snapshot.session.drafts, [id]: draft } },
        };
      }
      this.publish({ saving: this.dirty.size ? 'dirty' : 'saved', error: this.snapshot.error?.code.startsWith('draft_') ? null : this.snapshot.error });
      this.scheduleSave();
    } catch (error) {
      const value = failure(error);
      this.publish({ saving: 'error', error: { code: value.code, message: `Черновик пока не сохранён. Ввод остаётся на экране; не закрывайте приложение. ${value.message}` } });
      throw error;
    }
  }

  flush = async () => {
    if (this.saveTimer !== null) clearTimeout(this.saveTimer);
    this.saveTimer = null;
    return this.enqueue(() => this.saveDrafts());
  };

  leave = async () => {
    try {
      await this.flush();
      return this.dirty.size === 0;
    } catch {
      return false;
    }
  };

  retrySave = async () => {
    if (this.snapshot.busy) return;
    try {
      const session = await this.enqueue(() => this.runtime.session(this.snapshot.session.id));
      try {
        this.publish({ ...pendingOperations(session), queueError: null });
      } catch (error) {
        const value = failure(error);
        this.publish({ queueError: value, error: value });
        return;
      }
      this.adopt(session);
      await this.flush();
      this.publish({ error: null });
    } catch (error) {
      this.publish({ error: failure(error), saving: 'error' });
    }
  };

  private adopt(session: Session) {
    const drafts = { ...this.snapshot.drafts };
    for (const task of session.tasks) {
      if (!this.dirty.has(task.id)) {
        drafts[task.id] = { ...(session.drafts[task.id] ?? drafts[task.id] ?? { answer: '', active_seconds: 0 }) };
        this.elapsed.set(task.id, Math.max(this.elapsed.get(task.id) ?? 0, drafts[task.id].active_seconds * 1000));
      }
    }
    this.publish({ session, drafts });
  }

  submit = async (skipped = false) => {
    if (this.snapshot.busy || this.snapshot.queueError || this.snapshot.pendingFinish
      || (this.snapshot.session.status !== 'active' && !this.snapshot.pendingAttempt)) return;
    const id = this.currentTaskId();
    if (!id) return;
    this.checkpoint();
    let pending = this.snapshot.pendingAttempt;
    try {
      if (!pending) {
        const draft = this.snapshot.drafts[id];
        pending = { version: '1', key: operationKey(), body: { task_id: id, answer: skipped ? '' : draft.answer, active_seconds: draft.active_seconds, skipped } };
        writeOperation('attempt', this.snapshot.session.id, pending);
      }
    } catch (error) {
      this.publish({ error: failure(error) });
      return;
    }
    this.publish({ pendingAttempt: pending, busy: 'attempt', error: null, formError: null });
    try {
      await this.enqueue(async () => {
        await this.saveDrafts();
        await this.runtime.attempt(this.snapshot.session.id, pending.body, pending.key);
        this.adopt(await this.runtime.session(this.snapshot.session.id));
      });
      acknowledgeOperation('attempt', this.snapshot.session.id);
      this.publish({ pendingAttempt: null });
    } catch (error) {
      const value = failure(error);
      if (isAnswerFormatFailure(value)) {
        this.publish({ formError: value });
        try {
          acknowledgeOperation('attempt', this.snapshot.session.id);
          this.publish({ pendingAttempt: null });
        }
        catch (storageError) { this.publish({ error: failure(storageError) }); }
      } else {
        this.publish({ error: value });
      }
    } finally {
      this.publish({ busy: null });
    }
  };

  move = async (index: number) => {
    if (this.snapshot.busy || this.snapshot.queueError || this.snapshot.pendingAttempt || this.snapshot.pendingFinish || this.snapshot.session.status !== 'active') return;
    if (index < 0 || index >= this.snapshot.session.tasks.length || index === this.snapshot.session.current_index) return;
    this.checkpoint();
    this.clockStarted = null;
    this.publish({ busy: 'position', error: null, formError: null });
    try {
      await this.enqueue(async () => {
        await this.saveDrafts();
        const session = await this.runtime.position(this.snapshot.session.id, index);
        this.adopt(session);
      });
    } catch (error) {
      this.publish({ error: failure(error) });
    } finally {
      this.publish({ busy: null });
      this.clockStarted = null;
      this.checkpoint();
    }
  };

  help = async (kind: 'hint' | 'solution') => {
    if (this.snapshot.busy || this.snapshot.queueError || this.snapshot.pendingAttempt || this.snapshot.pendingFinish || this.snapshot.session.status !== 'active') return;
    const id = this.currentTaskId();
    if (!id) return;
    this.publish({ busy: kind, error: null });
    try {
      await this.enqueue(async () => {
        await this.saveDrafts();
        if (kind === 'solution') await this.runtime.solution(this.snapshot.session.id, id);
        else {
          const hints = this.snapshot.session.help[id]?.hints ?? [];
          const level = ([1, 2, 3] as const).find((candidate) => !hints.some((hint) => hint.level === candidate));
          if (level) await this.runtime.hint(this.snapshot.session.id, id, level);
        }
        this.adopt(await this.runtime.session(this.snapshot.session.id));
      });
    } catch (error) {
      this.publish({ error: failure(error) });
    } finally {
      this.publish({ busy: null });
    }
  };

  finish = async (): Promise<Session | null> => {
    if (this.snapshot.busy || this.snapshot.queueError || this.snapshot.pendingAttempt
      || (this.snapshot.session.status !== 'active' && !this.snapshot.pendingFinish)) return null;
    this.checkpoint();
    let pending = this.snapshot.pendingFinish;
    try {
      if (!pending) {
        pending = { version: '1', key: operationKey(), body: { session_id: this.snapshot.session.id } };
        writeOperation('finish', this.snapshot.session.id, pending);
      }
    } catch (error) {
      this.publish({ error: failure(error) });
      return null;
    }
    this.clockStarted = null;
    this.publish({ pendingFinish: pending, busy: 'finish', error: null });
    try {
      const session = await this.enqueue(async () => {
        await this.saveDrafts();
        return this.runtime.finish(this.snapshot.session.id, pending.key);
      });
      this.adopt(session);
      acknowledgeOperation('finish', session.id);
      this.publish({ pendingFinish: null, saving: 'saved' });
      return session;
    } catch (error) {
      this.publish({ error: failure(error) });
      return null;
    } finally {
      this.publish({ busy: null });
    }
  };
}
