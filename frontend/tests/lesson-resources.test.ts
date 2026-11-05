import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Lesson, Profile } from '../src/api/types';

function profileFixture(revision = 'opened-revision'): Profile {
  return {
    id: 'lesson-cache-profile', year: 2027, title: 'Учебный профиль', status: 'draft', revision,
    verified_at: '2026-11-05', verification_note: 'Учебный профиль.', source_urls: [],
    demo_mode: true, bank_size: 1,
    slots: [{
      id: 'distribution', number: 6, title: 'Распределения', level: 'П', summary: 'Чтение таблицы.',
      skills: [{ id: 'expectation', title: 'Среднее значение' }], available_tasks: 1, lesson_id: 'distribution/table',
    }],
  };
}

function lessonFixture(title = 'Среднее по таблице'): Lesson {
  return {
    id: 'distribution/table', title, slot: 6, slot_id: 'distribution', minutes: 5,
    skill_ids: ['expectation'], sections: [{ heading: 'Прочитайте таблицу', body: 'Учитывайте вероятности значений.', formula: null }],
    example: { statement: 'Равновозможные значения 2 и 4.', steps: ['Найдите их среднее.'], answer: '3' },
    takeaway: 'Учитывайте каждую вероятность.',
  };
}

function serverReplies(profile: Profile, lesson = lessonFixture()) {
  const requests: string[] = [];
  let offline = false;
  let lessonUnavailable = false;
  const fetcher = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    requests.push(path);
    if (offline) throw new TypeError('Offline');
    if (path === '/api/v1/profile') return Response.json(profile);
    if (path === '/api/v1/lessons/6' || path === '/api/v1/lessons/by-id/distribution%2Ftable') return lessonUnavailable
      ? Response.json({ error: { code: 'lesson_unavailable', message: 'Урок недоступен.' } }, { status: 503 })
      : Response.json(lesson);
    throw new Error(`Unexpected request: ${path}`);
  });
  vi.stubGlobal('fetch', fetcher);
  return { requests, offline: () => { offline = true; }, unavailableLesson: () => { lessonUnavailable = true; } };
}

beforeEach(() => { vi.resetModules(); });
afterEach(() => { vi.unstubAllGlobals(); });

describe('revision-scoped opened lessons', () => {
  it.each([
    ['numbered topic', 6, undefined],
    ['stable lesson ID', 0, 'distribution/table'],
  ] as const)('restores an opened %s after offline reload without publishing the old profile as current', async (_name, slot, lessonId) => {
    const server = serverReplies(profileFixture());
    const online = await import('../src/app/resources');
    await online.profileResource.load();
    await online.lessonResource(slot, lessonId).load();
    server.offline();
    vi.resetModules();
    const reloaded = await import('../src/app/resources');
    const lesson = reloaded.lessonResource(slot, lessonId);
    await lesson.load();
    expect(lesson.getSnapshot()).toMatchObject({ data: lessonFixture(), cached: true, loading: false });
    expect(lesson.getSnapshot().error).toBeTruthy();
    expect(reloaded.profileResource.getSnapshot().data).toBeNull();
    expect(server.requests.every((path) => path === '/api/v1/profile' || path.startsWith('/api/v1/lessons/'))).toBe(true);
  });

  it.each([
    ['revision', profileFixture('new-revision')],
    ['profile ID', { ...profileFixture('guard-opened'), id: 'another-profile' }],
  ] as const)('never substitutes the old lesson after the current %s has been confirmed', async (_name, nextProfile) => {
    serverReplies(profileFixture('guard-opened'));
    const online = await import('../src/app/resources');
    await online.profileResource.load();
    await online.lessonResource(6).load();
    vi.resetModules();
    const current = serverReplies(nextProfile);
    current.unavailableLesson();
    const reloaded = await import('../src/app/resources');
    await reloaded.profileResource.load();
    const lesson = reloaded.lessonResource(6);
    await lesson.load();
    expect(lesson.getSnapshot()).toMatchObject({ data: null, cached: false, loading: false });
    const { storage } = await import('../src/storage/database');
    expect((await storage.lesson(6, 'lesson-cache-profile:guard-opened'))?.lesson).toEqual(lessonFixture());
  });

  it('does not let a late response overwrite the opened snapshot under a departed catalog revision', async () => {
    const opened = lessonFixture('Ранее открытый урок');
    serverReplies(profileFixture('late-source'), opened);
    const online = await import('../src/app/resources');
    await online.profileResource.load();
    const oldResource = online.lessonResource(6);
    await oldResource.load();
    let resolveResponse!: (response: Response) => void;
    const pending = new Promise<Response>((resolve) => { resolveResponse = resolve; });
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === '/api/v1/profile') return Response.json(profileFixture('next-source'));
      if (String(input) === '/api/v1/lessons/6') return pending;
      throw new Error(`Unexpected request: ${String(input)}`);
    }));
    const lateRead = oldResource.load(true);
    await online.profileResource.load(true);
    resolveResponse(Response.json(lessonFixture('Урок из нового каталога')));
    await lateRead;
    const offline = serverReplies(profileFixture());
    offline.offline();
    vi.resetModules();
    const reloaded = await import('../src/app/resources');
    const lesson = reloaded.lessonResource(6);
    await lesson.load();
    expect(lesson.getSnapshot()).toMatchObject({ data: opened, cached: true });
  });

  it('does not replace the verified fallback with an unverified lesson write', async () => {
    serverReplies(profileFixture('verified-source'));
    const online = await import('../src/app/resources');
    await online.profileResource.load();
    await online.lessonResource(6).load();
    const { storage } = await import('../src/storage/database');
    await storage.saveLesson(lessonFixture('Неподтверждённый урок'));
    const offline = serverReplies(profileFixture());
    offline.offline();
    vi.resetModules();
    const reloaded = await import('../src/app/resources');
    const lesson = reloaded.lessonResource(6);
    await lesson.load();
    expect(lesson.getSnapshot()).toMatchObject({ data: lessonFixture(), cached: true });
  });

  it('does not broaden an opened revision into an unopened topic', async () => {
    const server = serverReplies(profileFixture('one-topic'));
    const online = await import('../src/app/resources');
    await online.profileResource.load();
    await online.lessonResource(6).load();
    server.offline();
    vi.resetModules();
    const reloaded = await import('../src/app/resources');
    const lesson = reloaded.lessonResource(7);
    await lesson.load();
    expect(lesson.getSnapshot()).toMatchObject({ data: null, cached: false, loading: false });
  });
});
