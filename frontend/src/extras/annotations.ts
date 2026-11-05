import { ApiError } from '../api/client';
import { annotationBody } from './api';
import { learningError } from './resource';
import type { AnnotationBody, AnnotationPatch, AnnotationValues, IdentityReader, LearningExtrasApi } from './types';

export type AnnotationSnapshot = {
  pending: { key: string; body: Readonly<AnnotationBody> } | null;
  saving: boolean;
  error: string | null;
  confirmed: AnnotationPatch;
  saved: boolean;
};

function empty(): AnnotationSnapshot {
  return { pending: null, saving: false, error: null, confirmed: {}, saved: false };
}

/** One serialized writer for one task. Retries send the frozen body with the same UUID. */
export class AnnotationWriter {
  private state = empty();
  private listeners = new Set<() => void>();
  private inFlight: Promise<void> | null = null;
  private disposed = false;
  private readonly owner: string | null;

  constructor(
    private readonly sessionId: string,
    private readonly taskId: string,
    private readonly api: Pick<LearningExtrasApi, 'annotate'>,
    private readonly identity: IdentityReader,
    private readonly onSaved: () => void,
    private readonly uuid: () => string = () => crypto.randomUUID(),
  ) { this.owner = identity.current(); }

  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  private patch(change: Partial<AnnotationSnapshot>) {
    this.state = { ...this.state, ...change };
    this.listeners.forEach((listener) => listener());
  }
  private current() { return !this.disposed && this.owner !== null && this.owner === this.identity.current(); }

  save = (change: AnnotationPatch): Promise<void> => {
    if (this.disposed) return Promise.resolve();
    if (!this.current()) {
      this.patch({ error: 'Начните занятие, чтобы сохранить отметку в своей истории.' });
      return Promise.resolve();
    }
    if (this.state.pending) return this.retry();
    try {
      const body = Object.freeze(annotationBody({ session_id: this.sessionId, task_id: this.taskId, ...change }));
      this.patch({ pending: { key: this.uuid(), body }, saved: false, error: null });
    } catch (error) {
      this.patch({ error: learningError(error) });
      return Promise.resolve();
    }
    return this.retry();
  };

  retry = (): Promise<void> => {
    if (!this.current() || !this.state.pending) return Promise.resolve();
    if (this.inFlight) return this.inFlight;
    const pending = this.state.pending;
    this.patch({ saving: true, error: null });
    this.inFlight = (async () => {
      try {
        const saved = await this.api.annotate(pending.body, pending.key);
        if (!this.current()) return;
        const { favourite, manual, not_understood, cause } = saved;
        this.patch({ pending: null, confirmed: { favourite, manual, not_understood, cause }, saved: true });
        this.onSaved();
      } catch (error) {
        if (!this.current()) return;
        const retryable = !(error instanceof ApiError) || error.retryable;
        this.patch({
          error: retryable
            ? 'Сохранение пока не подтверждено. Проверьте соединение и повторите: отметка не отправится дважды.'
            : learningError(error),
          pending: retryable ? pending : null,
        });
      } finally {
        if (this.current()) {
          this.inFlight = null;
          this.patch({ saving: false });
        }
      }
    })();
    return this.inFlight;
  };

  reconcile = (values: AnnotationValues) => {
    const keys = Object.keys(this.state.confirmed) as (keyof AnnotationPatch)[];
    if (!this.state.pending && !this.state.saving && keys.length && keys.every((key) => this.state.confirmed[key] === values[key])) this.patch({ confirmed: {} });
  };

  dispose = () => {
    this.disposed = true;
    this.inFlight = null;
    this.state = empty();
    this.listeners.forEach((listener) => listener());
  };
}
