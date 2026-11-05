import { EditorError, errorText } from './adapters';
import { prepareMutation, sendMutation } from './api';
import type { Mutation } from './api';

type Job = { request: Mutation; accept: (value: unknown) => void };
type Snapshot = { busy: boolean; uncertain: boolean; error: EditorError | null };

/** One in-memory writer per open editor. An uncertain write must resolve before another starts. */
export class EditorMutationQueue {
  private pending: Job | null = null;
  private state: Snapshot = { busy: false, uncertain: false, error: null };
  private listeners = new Set<() => void>();

  constructor(
    private actorId: string, private maxBytes: number,
    private send: (request: Mutation) => Promise<unknown> = sendMutation,
  ) {}

  getSnapshot = (): Snapshot => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  private update(state: Snapshot) {
    this.state = state;
    this.listeners.forEach(listener => listener());
  }

  private async execute(job: Job): Promise<void> {
    if (this.state.busy) return;
    const wasUncertain = this.state.uncertain;
    this.update({ busy: true, uncertain: wasUncertain, error: null });
    try {
      const value = await this.send(job.request);
      job.accept(value);
      this.pending = null;
      this.update({ busy: false, uncertain: false, error: null });
    } catch (failure) {
      const error = failure instanceof EditorError ? failure : new EditorError(errorText(failure), 'network', 0, null, true);
      // Auth/rate gates run before replay lookup. They cannot disprove an earlier commit.
      const uncertain = error.uncertain || (wasUncertain && [401, 403, 429].includes(error.status));
      if (!uncertain) this.pending = null;
      this.update({ busy: false, uncertain, error });
    }
  }

  run = (path: string, method: Mutation['method'], body: unknown, accept: Job['accept']): Promise<void> => {
    if (this.state.busy || this.pending) return Promise.resolve();
    try {
      const job = { request: prepareMutation(this.actorId, path, method, body, this.maxBytes), accept };
      this.pending = job;
      return this.execute(job);
    } catch (failure) {
      this.update({ busy: false, uncertain: false, error: failure instanceof EditorError ? failure : new EditorError(errorText(failure)) });
      return Promise.resolve();
    }
  };
  retry = (): Promise<void> => this.pending ? this.execute(this.pending) : Promise.resolve();
}
