import { AnnotationWriter } from './annotations';
import { ScopedResource } from './resource';
import type { IdentityReader, LearningExtrasApi, PlanMinutes } from './types';

export function createLearningStore(api: LearningExtrasApi, identity: IdentityReader, events: EventTarget) {
  let annotationGeneration = 0;
  const savedAnnotations = new ScopedResource(identity, () => {
    const generation = annotationGeneration;
    const owner = identity.current();
    return api.annotations(() => generation === annotationGeneration && owner !== null && owner === identity.current());
  });
  const dashboard = new ScopedResource(identity, api.dashboard);
  const pages = new Map<number, ScopedResource<Awaited<ReturnType<LearningExtrasApi['dashboard']>>>>();
  const progress = new ScopedResource(identity, api.progress);
  const plans = new Map(([10, 20, 30] as const).map((minutes) => [minutes, new ScopedResource(identity, () => api.plan(minutes))]));
  const annotations = new Map<string, AnnotationWriter>();

  const reset = () => {
    annotationGeneration += 1;
    annotations.forEach((writer) => writer.dispose());
    annotations.clear();
    savedAnnotations.reset();
    dashboard.reset();
    pages.forEach((resource) => resource.reset());
    progress.reset();
    plans.forEach((resource) => resource.reset());
  };
  events.addEventListener('math-ege:identity-change', reset);

  return {
    dashboard,
    savedAnnotations,
    dashboardPage(offset = 0) {
      if (offset === 0) return dashboard;
      let resource = pages.get(offset);
      if (!resource) {
        resource = new ScopedResource(identity, () => api.dashboard({ offset }));
        pages.set(offset, resource);
      }
      return resource;
    },
    progress,
    syncIdentity() { if (dashboard.getSnapshot().owner !== identity.current()) reset(); },
    plan(minutes: PlanMinutes) { return plans.get(minutes)!; },
    annotation(sessionId: string, taskId: string) {
      const key = JSON.stringify([identity.current(), sessionId, taskId]);
      let writer = annotations.get(key);
      if (!writer) {
        writer = new AnnotationWriter(sessionId, taskId, api, identity, () => {
          annotationGeneration += 1;
          void savedAnnotations.refreshAfterWrite();
          void dashboard.refreshAfterWrite();
          pages.forEach((resource) => { if (resource.getSnapshot().ready) void resource.refreshAfterWrite(); });
        });
        annotations.set(key, writer);
      }
      return writer;
    },
    dispose() {
      annotationGeneration += 1;
      events.removeEventListener('math-ege:identity-change', reset);
      annotations.forEach((writer) => writer.dispose());
      annotations.clear();
      savedAnnotations.reset(false);
      dashboard.reset(false);
      pages.forEach((resource) => resource.reset(false));
      progress.reset(false);
      plans.forEach((resource) => resource.reset(false));
    },
  };
}
