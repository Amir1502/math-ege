export type IdentityView = { id: string; kind: 'guest' | 'account'; owner_ids: string[] };
type IdentityState = { value: IdentityView | null; ready: boolean; changing: boolean; error: string | null; epoch: number };
type Resolver = () => Promise<IdentityView | null>;

const CACHE_KEY = 'math-ege:identity-v2';

export class IdentityManager {
  private state: IdentityState;
  private listeners = new Set<() => void>();
  private barriers = new Set<() => Promise<void>>();
  private refreshing: Promise<IdentityView | null> | null = null;
  private transitioning = false;

  constructor(
    private readonly resolve: Resolver,
    initial: IdentityView | null = null,
    private readonly adopt: (value: IdentityView) => Promise<void> = async () => undefined,
    private readonly publish: (value: IdentityView | null) => void = () => undefined,
  ) {
    this.state = { value: initial, ready: false, changing: false, error: null, epoch: 0 };
  }

  current = () => this.state.value?.id ?? null;
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  beforeChange(barrier: () => Promise<void>) {
    this.barriers.add(barrier);
    return () => { this.barriers.delete(barrier); };
  }
  private patch(change: Partial<IdentityState>) {
    this.state = { ...this.state, ...change };
    this.listeners.forEach((listener) => listener());
  }
  private async quiesce() {
    this.patch({ changing: true });
    await Promise.all([...this.barriers].map((barrier) => barrier()));
  }
  refresh = (): Promise<IdentityView | null> => {
    this.refreshing ??= this.readRemote().finally(() => { this.refreshing = null; });
    return this.refreshing;
  };
  private async readRemote() {
    try {
      const value = await this.resolve();
      const changed = this.current() !== (value?.id ?? null);
      if (changed && !this.state.changing) await this.quiesce();
      if (value) await this.adopt(value);
      this.patch({ value, ready: true, changing: false, error: null, epoch: this.state.epoch + Number(changed) });
      this.publish(value);
      return value;
    } catch {
      const ambiguous = this.state.changing;
      this.patch({
        value: ambiguous ? null : this.state.value, ready: true, changing: false,
        error: 'Не удалось подтвердить доступ. Локальные записи сохранены; подключитесь к сети и повторите.',
        epoch: this.state.epoch + Number(ambiguous),
      });
      if (ambiguous) this.publish(null);
      return null;
    }
  }
  async transition(action: () => Promise<unknown>): Promise<void> {
    if (this.transitioning) throw new Error('Смена доступа уже выполняется.');
    this.transitioning = true;
    try {
      await this.quiesce();
      if (this.refreshing) await this.refreshing;
      this.patch({ changing: true });
      try { await action(); }
      finally { await this.refresh(); }
    } finally {
      this.transitioning = false;
      if (this.state.changing) this.patch({ changing: false });
    }
  }
  async externalChange() {
    await this.quiesce();
    await this.refresh();
  }
}

function cachedIdentity(): IdentityView | null {
  try {
    const raw = globalThis.localStorage?.getItem(CACHE_KEY);
    return raw ? validIdentity(JSON.parse(raw)) : null;
  } catch { return null; }
}

function validIdentity(value: unknown): IdentityView | null {
  if (!value || typeof value !== 'object') return null;
  const candidate = value as Partial<IdentityView>;
  return typeof candidate.id === 'string' && ['guest', 'account'].includes(candidate.kind ?? '')
    && Array.isArray(candidate.owner_ids) && candidate.owner_ids.every((id) => typeof id === 'string')
    ? candidate as IdentityView : null;
}

export const identity = new IdentityManager(async () => {
  const response = await fetch('/api/v1/identity', { credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(15_000) });
  if (response.status === 401) return null;
  if (!response.ok) throw new Error('Identity unavailable');
  const value = validIdentity(await response.json());
  if (!value) throw new Error('Invalid identity');
  return value;
}, cachedIdentity(), async (value) => {
  const { adoptIdentity } = await import('./database');
  await adoptIdentity(value);
}, (value) => {
  try {
    const encoded = value ? JSON.stringify(value) : null;
    if (globalThis.localStorage?.getItem(CACHE_KEY) !== encoded) {
      if (encoded) globalThis.localStorage?.setItem(CACHE_KEY, encoded);
      else globalThis.localStorage?.removeItem(CACHE_KEY);
    }
  } catch { /* Identity remains in memory when browser persistence is unavailable. */ }
});

if (typeof window !== 'undefined') {
  let previous = identity.current();
  identity.subscribe(() => {
    const next = identity.current();
    if (next !== previous || identity.getSnapshot().changing) {
      previous = next;
      window.dispatchEvent(new Event('math-ege:identity-change'));
    }
  });
  window.addEventListener('storage', (event) => {
    if (event.key === CACHE_KEY) void identity.externalChange();
  });
}
