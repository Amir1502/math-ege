import { OfflineError } from '../types';
import type { OfflineCourse, OfflineTask, StartBody } from '../types';

export const EXCLUSION_MS = 30 * 24 * 60 * 60 * 1000;

function invalidSelection(): never {
  throw new OfflineError('invalid_selection', 'Параметры серии не соответствуют встроенному курсу. Выберите номера, длину и доступные фильтры заново.');
}

function list<T extends string | number>(value: unknown, allowed: T[]): T[] {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.length > allowed.length || new Set(value).size !== value.length
    || value.some((item) => !allowed.includes(item))) invalidSelection();
  return value as T[];
}

function shuffle<T>(values: T[]): T[] {
  const result = [...values];
  for (let index = result.length - 1; index > 0; index--) {
    const other = Math.floor(crypto.getRandomValues(new Uint32Array(1))[0] / 2 ** 32 * (index + 1));
    [result[index], result[other]] = [result[other], result[index]];
  }
  return result;
}

export function selectTasks(course: OfflineCourse, body: StartBody, seen: Map<string, number>, now: number) {
  const allowedKeys = ['slots', 'length', 'mode', 'skill_ids', 'family_ids', 'difficulty', 'selection', 'repeat_task_id', 'until_stopped', 'target_minutes'];
  if (!body || body.mode !== 'practice' || ![5, 10, 20].includes(body.length)
    || Object.keys(body).some((key) => !allowedKeys.includes(key))
    || (body.difficulty != null && ![1, 2, 3].includes(body.difficulty))
    || (body.selection !== undefined && !['balanced', 'mixed'].includes(body.selection))
    || (body.until_stopped !== undefined && body.until_stopped !== false) || body.target_minutes != null) invalidSelection();
  const slots = list(body.slots, course.profile.slots.map((slot) => slot.number));
  const skills = list(body.skill_ids, [...new Set(course.profile.slots.flatMap((slot) => slot.skills.map((skill) => skill.id)))]);
  const families = list(body.family_ids, [...new Set(course.tasks.map((task) => task.family_id))]);
  const matching = course.tasks.filter((task) => (!slots.length || slots.includes(task.slot))
    && (!skills.length || skills.some((skill) => task.skill_ids.includes(skill)))
    && (!families.length || families.includes(task.family_id)) && (body.difficulty == null || task.difficulty === body.difficulty));
  if (body.repeat_task_id != null) {
    const task = matching.find((task) => task.id === body.repeat_task_id);
    if (!task) invalidSelection();
    return { tasks: [task], familiar: [task.id], notice: 'Явный повтор одного знакомого условия. Он не добавляет второе самостоятельное достижение.' };
  }
  const identities = new Set<string>();
  const pool = shuffle(matching).filter((task) => {
    if (identities.has(task.instance_key) || (seen.get(task.instance_key) ?? -Infinity) > now - EXCLUSION_MS) return false;
    identities.add(task.instance_key);
    return true;
  });
  if (!pool.length) throw new OfflineError('bank_exhausted', 'Новых условий по этим фильтрам не осталось. Расширьте выбор или откройте явно отмеченный повтор.');
  const tasks: OfflineTask[] = [];
  const slotCounts = new Map<number, number>();
  const familyCounts = new Map<string, number>();
  while (pool.length && tasks.length < body.length) {
    let index = 0;
    if (body.selection !== 'mixed') {
      const score = (task: OfflineTask) => (slotCounts.get(task.slot) ?? 0) * 100 + (familyCounts.get(task.family_id) ?? 0);
      for (let candidate = 1; candidate < pool.length; candidate++) if (score(pool[candidate]) < score(pool[index])) index = candidate;
    }
    const [task] = pool.splice(index, 1);
    tasks.push(task);
    slotCounts.set(task.slot, (slotCounts.get(task.slot) ?? 0) + 1);
    familyCounts.set(task.family_id, (familyCounts.get(task.family_id) ?? 0) + 1);
  }
  const familiar = tasks.filter((task) => seen.has(task.instance_key)).map((task) => task.id);
  const notices = [tasks.length < body.length ? `Доступно ${tasks.length} из ${body.length} запрошенных задач. Знакомые за последние 30 дней не подмешаны.` : null,
    familiar.length ? 'Часть условий встречалась раньше. Их повтор не добавляет новое самостоятельное достижение.' : null];
  return { tasks, familiar, notice: notices.filter(Boolean).join(' ') || null };
}
