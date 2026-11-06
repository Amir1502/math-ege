import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it, vi } from 'vitest';
import { loadOfflineCourse } from '../src/offline/content';
import { courseRoot, pythonJson } from './offline-core-python';

const frontendRoot = fileURLToPath(new URL('../', import.meta.url));
const packageScript = resolve(frontendRoot, 'scripts/package-offline.mjs');
const output = mkdtempSync(resolve(process.env.TEMP ?? process.env.TMP ?? frontendRoot, 'offline-core-course-'));

describe('verified data-only offline course', () => {
  it('packages unchanged bytes and build-time Python identities, then fetches only four relative assets', { timeout: 120_000 }, async () => {
    execFileSync(process.execPath, [packageScript, output], { cwd: frontendRoot, timeout: 120_000 });
    for (const name of ['profile.json', 'lessons.json', 'tasks.json']) {
      expect(readFileSync(resolve(output, name))).toEqual(readFileSync(resolve(courseRoot, name)));
    }
    const fetch = vi.fn(async (url: string) => {
      expect(url).toMatch(/^\.\/course\/(manifest|profile|lessons|tasks)\.json$/u);
      return new Response(readFileSync(resolve(output, url.slice('./course/'.length))));
    });
    vi.stubGlobal('fetch', fetch);
    try {
      const course = await loadOfflineCourse();
      expect(fetch.mock.calls.map(([url]) => url).sort()).toEqual([
        './course/lessons.json', './course/manifest.json', './course/profile.json', './course/tasks.json',
      ]);
      expect(course.version).toBe('1');
      expect(course.tasks).toHaveLength(845);
      expect(course.lessons).toHaveLength(99);
      expect(course.profile.slots.map((slot) => slot.number)).toEqual(Array.from({ length: 13 }, (_, index) => index + 1));
      expect(course.profile).toMatchObject({ status: 'draft', demo_mode: true, bank_size: 845 });
      expect(course.tasks.every((task) => task.review_status === 'demo' && task.source.reviewed_by === null)).toBe(true);
      const oracle = pythonJson<{ tasks: unknown[]; lessons: unknown[]; profile: unknown }>(`
import json
from app.content import load_content
from app.instances import instance_key
bundle = load_content()
print(json.dumps({'profile': bundle.public_profile(allow_demo_content=True).model_dump(mode='json'),
                  'lessons': [lesson.model_dump(mode='json') for lesson in bundle.lessons],
                  'tasks': [{**task.model_dump(mode='json'), 'instance_key': instance_key(task)}
                            for task in bundle.tasks]}, ensure_ascii=True))
`);
      expect(course.tasks).toEqual(oracle.tasks);
      expect(course.lessons).toEqual(oracle.lessons);
      expect(course.profile).toEqual(oracle.profile);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
