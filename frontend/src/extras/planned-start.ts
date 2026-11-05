import { api, ApiError } from '../api/client';
import { startSession } from '../learning/start-session';
import { scopedStorage } from '../storage/database';
import { identity } from '../storage/identity';
import { learningStore } from './hooks';
import { mixedStartBody } from './view-models';
import type { PlanMinutes } from './types';

let starting: Promise<string> | null = null;

/** Guest creation is restricted to this explicit start action. */
export function beginPlannedPractice(minutes: PlanMinutes): Promise<string> {
  if (starting) return starting;
  starting = (async () => {
    if (identity.getSnapshot().changing) throw new ApiError(409, 'identity_changed', 'Дождитесь завершения смены доступа.');
    if (!identity.current()) {
      await api.guest();
      await identity.refresh();
    }
    const owner = identity.current();
    if (!owner || identity.getSnapshot().changing) throw new ApiError(401, 'identity_required', 'Не удалось подтвердить доступ. Повторите начало занятия.');
    const pending = await scopedStorage(owner).pendingStart();
    let body = pending?.body;
    if (!body) {
      const resource = learningStore.plan(minutes);
      await resource.load(true);
      const plan = resource.getSnapshot();
      if (plan.error || !plan.data) throw new ApiError(0, 'plan_unavailable', plan.error ?? 'Не удалось рассчитать план. Повторите начало занятия.');
      if (!plan.data.slots.length) throw new ApiError(409, 'bank_exhausted', 'Для этого плана пока нет доступных задач. Выберите другие номера в практике.');
      body = mixedStartBody(plan.data);
    }
    if (identity.current() !== owner || identity.getSnapshot().changing) throw new ApiError(409, 'identity_changed', 'Доступ изменился. Откройте план заново.');
    const id = await startSession(body);
    if (identity.current() !== owner || identity.getSnapshot().changing) throw new ApiError(409, 'identity_changed', 'Доступ изменился. Откройте план заново.');
    return id;
  })().finally(() => { starting = null; });
  return starting;
}
