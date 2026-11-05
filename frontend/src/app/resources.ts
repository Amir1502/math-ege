import { useEffect, useSyncExternalStore } from 'react';
import { api, ApiError, errorText } from '../api/client';
import type { Lesson, Profile, Progress } from '../api/types';
import { storage } from '../storage/database';

export type ResourceState<T> = { data: T | null; loading: boolean; error: string | null; cached: boolean };

export class Resource<T> {
  private state: ResourceState<T> = { data: null, loading: true, error: null, cached: false };
  private listeners = new Set<() => void>();
  private inFlight: Promise<void> | null = null;
  private loaded = false;

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
    this.inFlight = (async () => {
      if (!this.state.data && this.cached) {
        const data = await this.cached().catch(() => undefined);
        if (data) this.patch({ data, cached: true, loading: false });
      }
      try {
        const data = await this.fetcher();
        this.patch({ data, cached: false, error: null });
        if (this.save) await this.save(data).catch(() => undefined);
      } catch (error) {
        this.patch({ error: errorText(error) });
      } finally {
        this.loaded = true;
        this.patch({ loading: false });
        this.inFlight = null;
      }
    })();
    return this.inFlight;
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

const lessons = new Map<number, Resource<Lesson>>();
export function lessonResource(slot: number) {
  let resource = lessons.get(slot);
  if (!resource) {
    resource = new Resource(
      () => api.lesson(slot),
      async () => (await storage.lesson(slot))?.lesson,
      (lesson) => storage.saveLesson(lesson),
    );
    lessons.set(slot, resource);
  }
  return resource;
}

export function useResource<T>(resource: Resource<T>, refresh = false) {
  const value = useSyncExternalStore(resource.subscribe, resource.getSnapshot);
  useEffect(() => { void resource.load(refresh); }, [resource, refresh]);
  return { ...value, retry: () => resource.load(true) };
}
