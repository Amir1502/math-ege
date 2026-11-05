import { useEffect, useSyncExternalStore } from 'react';
import { api, ApiError, errorText, request } from '../api/client';
import type { Lesson, Profile, Progress } from '../api/types';
import { cachedLessonRevision, storage } from '../storage/database';
import { identity } from '../storage/identity';

export type ResourceState<T> = { data: T | null; loading: boolean; error: string | null; cached: boolean };

export class Resource<T> {
  private state: ResourceState<T> = { data: null, loading: true, error: null, cached: false };
  private listeners = new Set<() => void>();
  private inFlight: Promise<void> | null = null;
  private loaded = false;
  private generation = 0;

  constructor(
    private readonly fetcher: () => Promise<T>,
    private readonly cached?: () => Promise<T | undefined>,
    private readonly save?: (value: T) => Promise<void>,
  ) {}

  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  private patch(change: Partial<ResourceState<T>>) {
    this.state = { ...this.state, ...change };
    this.listeners.forEach((listener) => listener());
  }
  load(force = false) {
    if (this.inFlight) return this.inFlight;
    if (this.loaded && !force) return Promise.resolve();
    this.patch({ loading: !this.state.data, error: null });
    const generation = this.generation;
    this.inFlight = (async () => {
      if (!this.state.data && this.cached) {
        const data = await this.cached().catch(() => undefined);
        if (data && generation === this.generation) this.patch({ data, cached: true, loading: false });
      }
      try {
        const data = await this.fetcher();
        if (generation !== this.generation) return;
        this.patch({ data, cached: false, error: null });
        if (this.save) await this.save(data).catch(() => undefined);
      } catch (error) {
        if (generation === this.generation) this.patch({ error: errorText(error) });
      } finally {
        if (generation === this.generation) {
          this.loaded = true;
          this.patch({ loading: false });
          this.inFlight = null;
        }
      }
    })();
    return this.inFlight;
  }

  reset() {
    this.generation += 1;
    this.loaded = false;
    this.inFlight = null;
    this.patch({ data: null, loading: true, error: null, cached: false });
  }
}

export const profileResource = new Resource<Profile>(api.profile);
export const progressResource = new Resource<Progress | null>(async () => {
  try { return await api.progress(); }
  catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
});

identity.beforeChange(async () => { progressResource.reset(); });

const lessons = new Map<string, Resource<Lesson>>();
export function lessonResource(slot: number, lessonId?: string) {
  const profile = profileResource.getSnapshot().data;
  const revision = profile ? `${profile.id}:${profile.revision}` : 'unverified';
  const key = `${revision}:${lessonId ?? slot}`;
  let resource = lessons.get(key);
  if (!resource) {
    resource = new Resource(
      () => lessonId ? request<Lesson>(`/lessons/by-id/${encodeURIComponent(lessonId)}`) : api.lesson(slot),
      async () => {
        await profileResource.load();
        const current = profileResource.getSnapshot().data;
        const cachedRevision = current ? `${current.id}:${current.revision}` : await cachedLessonRevision();
        if (!cachedRevision || (revision !== 'unverified' && cachedRevision !== revision)) return undefined;
        return (await storage.lesson(lessonId ?? slot, cachedRevision))?.lesson;
      },
      (lesson) => {
        const current = profileResource.getSnapshot().data;
        return current && revision === `${current.id}:${current.revision}`
          ? storage.saveLesson(lesson, revision, lessonId ?? slot)
          : Promise.resolve();
      },
    );
    lessons.set(key, resource);
  }
  return resource;
}

export function useResource<T>(resource: Resource<T>, refresh = false) {
  const value = useSyncExternalStore(resource.subscribe, resource.getSnapshot);
  useEffect(() => { void resource.load(refresh); }, [resource, refresh]);
  return { ...value, retry: () => resource.load(true) };
}
