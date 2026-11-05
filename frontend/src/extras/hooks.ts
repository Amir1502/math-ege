import { useEffect, useState, useSyncExternalStore } from 'react';
import { identity } from '../storage/identity';
import { scopedStorage } from '../storage/database';
import { learningExtrasApi } from './api';
import { confirmedLearningOwner } from './identity';
import { createLearningStore } from './store';
import type { ScopedResource } from './resource';
import type { PlanMinutes } from './types';

const learningIdentity = { current: confirmedLearningOwner };

export const learningStore = createLearningStore(learningExtrasApi, learningIdentity, typeof window === 'undefined' ? new EventTarget() : window);
const unsubscribe = identity.subscribe(learningStore.syncIdentity);
if (import.meta.hot) import.meta.hot.dispose(() => { unsubscribe(); learningStore.dispose(); });

export function useLearningIdentity() {
  const owner = useSyncExternalStore(identity.subscribe, learningIdentity.current);
  useEffect(() => { void identity.refresh(); }, []);
  return owner;
}

function useLearningResource<T>(resource: ScopedResource<T>, refresh = true) {
  const value = useSyncExternalStore(resource.subscribe, resource.getSnapshot);
  useEffect(() => { void resource.load(refresh); }, [resource, refresh]);
  return { ...value, retry: resource.retry };
}

export function useLearningDashboard(offset = 0) { return useLearningResource(learningStore.dashboardPage(offset)); }
export function useSavedAnnotations() { return useLearningResource(learningStore.savedAnnotations); }
export function usePracticeProgress() { return useLearningResource(learningStore.progress); }
export function useTimePlan(minutes: PlanMinutes) { return useLearningResource(learningStore.plan(minutes)); }

export function useTaskAnnotations(sessionId: string, taskId: string) {
  const owner = useLearningIdentity();
  const writer = learningStore.annotation(sessionId, taskId);
  const state = useSyncExternalStore(writer.subscribe, writer.getSnapshot);
  return { ...state, available: owner !== null, save: writer.save, retry: writer.retry, reconcile: writer.reconcile };
}

/** Only the ID is retained here; session/answer snapshots stay in scoped storage. */
export function useLocalActivePractice() {
  const owner = useLearningIdentity();
  const [active, setActive] = useState<{ owner: string; id: string } | null>(null);
  useEffect(() => {
    if (!owner) return;
    let alive = true;
    const storage = scopedStorage(owner);
    void storage.active().then(async (id) => {
      if (!id) return;
      const record = await storage.session(id);
      if (alive && learningIdentity.current() === owner && record?.session.status === 'active') setActive({ owner, id });
    }).catch(() => undefined);
    return () => { alive = false; };
  }, [owner]);
  return active?.owner === owner ? active.id : null;
}

/** Read the assessment module's pointer; retain no drafts or result snapshots. */
export function useLocalAssessmentContinuation() {
  const owner = useLearningIdentity();
  const [saved, setSaved] = useState<{ owner: string; id: string } | null>(null);
  useEffect(() => {
    if (!owner) return;
    let alive = true;
    void (async () => {
      const { assessmentRepository } = await import('../assessments/runtime');
      const repository = assessmentRepository();
      const id = await repository.last(owner);
      if (!id || !alive || learningIdentity.current() !== owner) return;
      const { assessmentDevice } = await import('../assessments/device');
      const device = await assessmentDevice();
      const record = await repository.load(owner, id, device);
      if (record && (record.owner_id !== owner || record.device_id !== device || record.view.id !== id || record.view.status === 'completed')) return;
      if (alive && learningIdentity.current() === owner) setSaved({ owner, id });
    })().catch(() => undefined);
    return () => { alive = false; };
  }, [owner]);
  return saved?.owner === owner ? saved.id : null;
}
