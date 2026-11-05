import { ApiError } from '../api/client';
import type { IdentityReader, ResourceSnapshot } from './types';

export function learningError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return 'Доступ к истории изменился. Начните занятие или войдите снова.';
    if (error.status === 0) return 'Нет связи с сервером. Проверьте соединение и повторите запрос.';
    if (error.status === 404) return 'Эта учебная запись сейчас недоступна. Обновите список.';
    return error.message;
  }
  return 'Не удалось получить ответ сервера. Повторите запрос.';
}

/** In-memory only. A generation also protects an A -> B -> A identity change. */
export class ScopedResource<T> {
  private state: ResourceSnapshot<T>;
  private listeners = new Set<() => void>();
  private generation = 0;
  private inFlight: Promise<void> | null = null;

  constructor(private readonly identity: IdentityReader, private readonly fetcher: () => Promise<T>) {
    this.state = this.empty();
  }

  private empty(): ResourceSnapshot<T> {
    const owner = this.identity.current();
    return { owner, data: null, loading: owner !== null, ready: owner === null, error: null };
  }

  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  private patch(change: Partial<ResourceSnapshot<T>>) {
    this.state = { ...this.state, ...change };
    this.listeners.forEach((listener) => listener());
  }

  reset = (reload = true) => {
    this.generation += 1;
    this.inFlight = null;
    this.state = this.empty();
    this.listeners.forEach((listener) => listener());
    if (reload && this.listeners.size > 0) void this.load();
  };

  load = (force = false): Promise<void> => {
    if (this.state.owner !== this.identity.current()) this.reset(false);
    if (!this.state.owner || (this.state.ready && !force)) return Promise.resolve();
    if (this.inFlight) return this.inFlight;
    const owner = this.state.owner;
    const generation = this.generation;
    const current = () => generation === this.generation && owner === this.identity.current();
    this.patch({ loading: true, error: null });

    this.inFlight = (async () => {
      try {
        const data = await this.fetcher();
        if (current()) this.patch({ data, error: null });
      } catch (error) {
        if (!current()) return;
        if (error instanceof ApiError && error.status === 401) this.patch({ data: null, error: null });
        else this.patch({ error: learningError(error) });
      } finally {
        if (current()) {
          this.inFlight = null;
          this.patch({ loading: false, ready: true });
        }
      }
    })();
    return this.inFlight;
  };

  retry = () => this.load(true);

  refreshAfterWrite = () => {
    this.generation += 1;
    this.inFlight = null;
    return this.load(true);
  };
}
