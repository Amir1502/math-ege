import { api as commonApi, ApiError } from '../api/client';
import { identity } from '../storage/identity';
import { createAssessmentApi } from './api';
import { AssessmentController } from './controller';
import { AssessmentPreparation } from './prepare';
import { AssessmentRepository } from './storage';
import type { AssessmentMode } from './types';

let repository: AssessmentRepository | undefined;
const controllers = new Map<string, { controller: AssessmentController; timer: ReturnType<typeof setInterval> }>();
const preparations = new Map<string, AssessmentPreparation>();

export function assessmentRepository(): AssessmentRepository {
  repository ??= new AssessmentRepository();
  return repository;
}

function assertOwner(ownerId: string) {
  if (identity.getSnapshot().changing || identity.current() !== ownerId) {
    throw new ApiError(409, 'identity_changed', 'Доступ изменился. Откройте вариант заново в текущем профиле.');
  }
}

export function assessmentController(ownerId: string, id: string, deviceId: string): AssessmentController {
  assertOwner(ownerId);
  const key = JSON.stringify([ownerId, id, deviceId]);
  let entry = controllers.get(key);
  if (!entry) {
    const controller = new AssessmentController(id, ownerId, deviceId, createAssessmentApi(ownerId), assessmentRepository());
    const timer = setInterval(() => {
      const status = controller.getSnapshot().record?.view.status;
      if (status === 'active' || status === 'awaiting_snapshot') controller.tick();
      if (status === 'completed') clearInterval(timer);
    }, 500);
    entry = { controller, timer };
    controllers.set(key, entry);
  }
  return entry.controller;
}

export function assessmentPreparation(ownerId: string, deviceId: string): AssessmentPreparation {
  assertOwner(ownerId);
  const key = JSON.stringify([ownerId, deviceId]);
  let preparation = preparations.get(key);
  if (!preparation) {
    preparation = new AssessmentPreparation(ownerId, deviceId, createAssessmentApi(ownerId), assessmentRepository());
    preparations.set(key, preparation);
  }
  return preparation;
}

export async function prepareAssessment(mode: AssessmentMode, minutes: number, deviceId: string): Promise<string> {
  if (identity.getSnapshot().changing) throw new ApiError(409, 'identity_changed', 'Дождитесь смены профиля.');
  const before = identity.current();
  // Guest creation is intentional, only from the setup action. Identity supplies the
  // canonical scope after guest/account linking; no token is stored by this module.
  await commonApi.guest();
  const owner = await identity.refresh();
  if (!owner || (before && owner.id !== before)) throw new ApiError(409, 'identity_changed', 'Не удалось подтвердить текущий профиль. Повторите подготовку.');
  assertOwner(owner.id);
  const preparation = assessmentPreparation(owner.id, deviceId);
  const id = await preparation.prepare(mode, minutes);
  assertOwner(owner.id);
  return id;
}

identity.beforeChange(async () => {
  preparations.forEach((preparation) => preparation.suspend());
  preparations.clear();
  const previous = [...controllers.values()];
  controllers.clear();
  previous.forEach(({ timer }) => clearInterval(timer));
  await Promise.all(previous.map(({ controller }) => controller.suspend()));
});

if (typeof window !== 'undefined') {
  window.addEventListener('online', () => controllers.forEach(({ controller }) => controller.setOnline(true)));
  window.addEventListener('offline', () => controllers.forEach(({ controller }) => controller.setOnline(false)));
  window.addEventListener('pagehide', () => controllers.forEach(({ controller }) => {
    controller.setVisible(false);
    void controller.persist().catch(() => undefined);
  }));
  window.addEventListener('pageshow', () => controllers.forEach(({ controller }) => controller.tick()));
  window.addEventListener('focus', () => controllers.forEach(({ controller }) => {
    controller.tick();
    if (controller.getSnapshot().record?.view.status !== 'completed') void controller.refresh();
  }));
}
