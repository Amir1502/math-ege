import { OfflineError } from './types';
import type { OfflineCourse } from './types';
import { array, HASH, integer, invalid, lessonData, object, profileData, safeData, taskData, text, validateLinks } from './core/validation';

export type { OfflineCourse, OfflineTask } from './types';

const ASSETS = ['profile.json', 'lessons.json', 'tasks.json'] as const;
const LIMITS = { 'manifest.json': 1_048_576, 'profile.json': 131_072, 'lessons.json': 2_097_152, 'tasks.json': 8_388_608 };

async function bytes(name: keyof typeof LIMITS): Promise<ArrayBuffer> {
  const response = await fetch(`./course/${name}`, {
    method: 'GET', mode: 'same-origin', credentials: 'omit', redirect: 'error', cache: 'no-store',
  });
  if (!response.ok || response.redirected) throw new OfflineError('content_unavailable', 'Не удалось прочитать встроенный курс.');
  const result = await response.arrayBuffer();
  if (result.byteLength > LIMITS[name] || !result.byteLength) invalid('Неверный размер файла встроенного курса.');
  return result;
}

function json(raw: ArrayBuffer): unknown {
  return JSON.parse(new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(raw)) as unknown;
}

/** Four fixed local assets only. No cached fallback is accepted after a failed integrity check. */
export async function loadOfflineCourse(): Promise<OfflineCourse> {
  try {
    if (!globalThis.crypto?.subtle) throw new OfflineError('content_integrity', 'Проверка целостности курса недоступна.');
    const manifest = object(json(await bytes('manifest.json')));
    safeData(manifest, 100_000, LIMITS['manifest.json']);
    if (manifest.version !== '1') throw new OfflineError('unsupported_course_version', 'Версия встроенного курса не поддерживается.');
    const revision = text(manifest.package_revision, 1, 128);
    if (manifest.checker_revision !== 'fraction-v1' || manifest.instance_key_revision !== 'app.instances.instance_key-v1'
      || manifest.task_count !== 845 || manifest.lesson_count !== 99 || manifest.slot_count !== 13
      || manifest.review_status !== 'demo' || manifest.reviewed_by !== null) invalid();
    const files = object(manifest.files);
    if (Object.keys(files).length !== 3 || ASSETS.some((name) => !(name in files))) invalid();
    const values = await Promise.all(ASSETS.map(async (name) => {
      const entry = object(files[name]);
      const expected = text(entry.sha256);
      if (!HASH.test(expected)) invalid();
      const size = integer(entry.bytes, 1, LIMITS[name]);
      const raw = await bytes(name);
      const digest = await crypto.subtle.digest('SHA-256', raw);
      const actual = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
      if (raw.byteLength !== size || actual !== expected) {
        throw new OfflineError('content_integrity', 'Нарушена целостность встроенного курса. Практика не запущена.');
      }
      return json(raw);
    }));
    const instanceKeys = object(manifest.instance_keys);
    const tasks = array(values[2], 845, 845).map((value) => {
      const raw = object(value);
      const id = text(raw.id, 1, 128);
      if (!Object.prototype.hasOwnProperty.call(instanceKeys, id)) invalid();
      return taskData(raw, text(instanceKeys[id]));
    });
    if (Object.keys(instanceKeys).length !== tasks.length) invalid();
    const lessons = array(values[1], 99, 99).map(lessonData);
    const profile = profileData(values[0], tasks);
    if (profile.id !== manifest.profile_id || profile.revision !== manifest.profile_revision || profile.status !== 'draft'
      || profile.slots.length !== 13 || profile.slots.some((slot) => slot.number > 13 || !slot.available_tasks)
      || tasks.some((task) => task.review_status !== 'demo' || task.source.reviewed_by !== null)
       || lessons.some((lesson) => lesson.review_status !== 'demo' || lesson.reviewed_by !== null)) invalid();
    validateLinks(profile, lessons, tasks);
    return { version: '1', package_revision: revision, profile, lessons, tasks };
  } catch (error) {
    if (error instanceof OfflineError) throw error;
    throw new OfflineError('content_unavailable', 'Встроенный курс отсутствует, повреждён или не прошёл проверку.');
  }
}
