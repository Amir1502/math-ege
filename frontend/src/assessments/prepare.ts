import { ApiError } from '../api/client';
import { completeConditions } from './api';
import { createAssessmentRecord } from './model';
import type { AssessmentRepository } from './storage';
import type { AssessmentApi, AssessmentMode, Pending, PrepareBody } from './types';

type PreparationSnapshot = { busy: boolean; pending: Pending<PrepareBody> | null; error: unknown };

/** Preparation returns only after every public condition is durably available offline. */
export class AssessmentPreparation {
  private pending?: Promise<string>;
  private suspended = false;
  private state: PreparationSnapshot = { busy: false, pending: null, error: null };
  private listeners = new Set<() => void>();

  constructor(
    readonly ownerId: string,
    readonly deviceId: string,
    private readonly api: AssessmentApi,
    private readonly storage: AssessmentRepository,
  ) {}

  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };

  private publish(patch: Partial<PreparationSnapshot>) {
    if (this.suspended) return;
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }

  async restore() {
    const pending = await this.storage.pendingCreate(this.ownerId, this.deviceId);
    if (!this.state.busy) this.publish({ pending });
  }

  prepare(mode: AssessmentMode, durationMinutes: number): Promise<string> {
    if (this.pending) return this.pending;
    this.publish({ busy: true, error: null });
    this.pending = this.run(mode, durationMinutes).catch((error: unknown) => {
      this.publish({ error });
      throw error;
    }).finally(() => { this.pending = undefined; this.publish({ busy: false }); });
    return this.pending;
  }

  private guard() {
    if (this.suspended) throw new ApiError(409, 'identity_changed', 'Доступ изменился. Вернитесь к настройке варианта.');
  }

  private async run(mode: AssessmentMode, durationMinutes: number): Promise<string> {
    this.guard();
    if (!Number.isInteger(durationMinutes) || durationMinutes < 15 || durationMinutes > 180) {
      throw new ApiError(422, 'invalid_duration', 'Укажите целое число минут от 15 до 180.', 'duration_minutes');
    }
    let pending = await this.storage.pendingCreate(this.ownerId, this.deviceId);
    this.guard();
    if (!pending) pending = {
      key: crypto.randomUUID(), body: { mode, duration_minutes: durationMinutes, device_id: this.deviceId },
    };
    this.publish({ pending });
    await this.storage.savePendingCreate(this.ownerId, this.deviceId, pending);
    this.guard();
    const view = await this.api.prepare(pending.body, pending.key);
    this.guard();
    if (!completeConditions(view.tasks)) throw new ApiError(502, 'incomplete_assessment', 'Получены не все 13 условий. Повторите подготовку; время ещё не запущено.');
    const record = createAssessmentRecord(view, this.ownerId, this.deviceId);
    this.storage.journal(record);
    await this.storage.save(record);
    await this.storage.setLast(this.ownerId, view.id);
    this.guard();
    await this.storage.savePendingCreate(this.ownerId, this.deviceId, null);
    this.publish({ pending: null });
    return view.id;
  }

  suspend() { this.suspended = true; this.listeners.clear(); }
}
