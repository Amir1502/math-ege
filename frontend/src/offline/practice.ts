import { OfflineRepository } from './repository';
import type { Device, Exposure, SessionRecord, WriteTransaction } from './repository';
import { OfflineError } from './types';
import type { Attempt, AttemptBody, DraftBody, Hint, LearningSession, OfflineCourse, OfflineTask, ProfileSource, Solution, StartBody } from './types';
import { copy, publicTask, summary, UUID, uuid } from './core/model';
import { selectTasks } from './core/selection';
import { localProgress } from './progress';
import { checkAnswer, parseAnswer } from './checker';

function owned(record: SessionRecord, owner: string): SessionRecord {
  if (record.owner !== owner || record.schema !== 1 || record.origin !== 'device' || record.session.id !== record.id) {
    throw new OfflineError('storage_corrupt', 'Сохранённое занятие не принадлежит локальному профилю. История не изменялась.');
  }
  return record;
}

function payload(value: unknown): string {
  function sorted(item: unknown): unknown {
    if (Array.isArray(item)) return item.map(sorted);
    if (item && typeof item === 'object') return Object.fromEntries(Object.keys(item).sort().map((key) => [key, sorted((item as Record<string, unknown>)[key])]));
    if (item === null || ['string', 'boolean'].includes(typeof item) || (typeof item === 'number' && Number.isFinite(item))) return item;
    throw new OfflineError('invalid_request', 'Неверный формат локальной операции.');
  }
  const result = JSON.stringify(sorted(value));
  if (result.length > 16_384) throw new OfflineError('invalid_request', 'Локальная операция слишком велика.');
  return result;
}

function profileSnapshot(course: OfflineCourse): ProfileSource {
  const profile = course.profile;
  return { id: profile.id, year: profile.year, title: profile.title, status: profile.status,
    revision: profile.revision, verified_at: profile.verified_at, verification_note: profile.verification_note,
    source_urls: profile.source_urls, slots: profile.slots.map((slot) => ({ number: slot.number, id: slot.id,
      title: slot.title, level: slot.level, summary: slot.summary, skills: slot.skills, lesson_id: slot.lesson_id })) };
}

function boundedSeconds(value: number): number {
  if (!Number.isSafeInteger(value) || value < 0 || value > 86_400) {
    throw new OfflineError('invalid_active_seconds', 'Время решения должно быть целым числом от 0 до 86400 секунд.');
  }
  return value;
}

export class OfflineRuntime {
  private readonly repository = new OfflineRepository();
  private readonly course: OfflineCourse;

  constructor(course: OfflineCourse) { this.course = copy(course); }

  private async operation<T>(kind: string, key: string, body: unknown,
    action: (tx: WriteTransaction, device: Device) => Promise<T>): Promise<T> {
    if (!UUID.test(key)) return Promise.reject(new OfflineError('invalid_idempotency_key', 'Ключ операции должен быть отдельным UUID.'));
    const encoded = payload(body);
    return this.repository.write(async (tx, device) => {
      const store = tx.objectStore('operations');
      const id = `${device.owner}:${kind}:${key}`;
      const existing = await store.get(id);
      if (existing) {
        if (existing.owner !== device.owner || existing.payload !== encoded) {
          throw new OfflineError('idempotency_conflict', 'Этот ключ уже использован для других параметров. Исходная операция и история не изменялись.');
        }
        return copy(existing.result as T);
      }
      const result = await action(tx, device);
      await store.add({ owner: device.owner, payload: encoded, result }, id);
      return copy(result);
    });
  }

  private async active(tx: WriteTransaction, owner: string, id: string): Promise<SessionRecord> {
    const record = await tx.objectStore('sessions').get(id);
    if (!record) throw new OfflineError('session_not_found', 'Занятие не найдено на этом устройстве.');
    owned(record, owner);
    if (record.session.status !== 'active') throw new OfflineError('session_completed', 'Занятие завершено. Сохранённый итог нельзя изменить.');
    return record;
  }

  private task(record: SessionRecord, id: string) {
    const task = record.materials.find((task) => task.id === id);
    if (!task || !record.session.tasks.some((item) => item.id === id)) {
      throw new OfflineError('task_not_found', 'Задача не входит в сохранённое занятие.');
    }
    return task;
  }

  private async exposure(tx: WriteTransaction, owner: string, instanceKey: string): Promise<Exposure> {
    const exposure = await tx.objectStore('exposures').get(`${owner}:${instanceKey}`);
    if (!exposure || exposure.owner !== owner || exposure.instance_key !== instanceKey) {
      throw new OfflineError('storage_corrupt', 'Не удалось восстановить историю условия. Ответ не записывался.');
    }
    return exposure;
  }

  async state() {
    return this.repository.read(async (tx, device) => {
      const records = (await tx.objectStore('sessions').getAll()).map((record) => owned(record, device.owner));
      const sessions = records.map((record) => record.session).sort((a, b) => b.created_at.localeCompare(a.created_at));
      return { owner: device.owner, active_session_id: device.active_session_id, sessions };
    });
  }

  start(body: StartBody, key: string): Promise<LearningSession> {
    return this.operation('start', key, body, async (tx, device) => {
      const now = Date.now();
      const seen = new Map<string, number>();
      for (const exposure of await tx.objectStore('exposures').getAll()) {
        if (exposure.owner !== device.owner || !Number.isFinite(exposure.last_seen)) {
          throw new OfflineError('storage_corrupt', 'История встреченных условий повреждена. Новая серия не создавалась.');
        }
        seen.set(exposure.instance_key, exposure.last_seen);
      }
      const selected = selectTasks(this.course, body, seen, now);
      const id = uuid();
      const session: LearningSession = {
        id, profile_id: this.course.profile.id, profile_revision: this.course.profile.revision,
        profile: profileSnapshot(this.course), mode: 'practice', status: 'active', created_at: new Date(now).toISOString(),
        completed_at: null, current_index: 0, requested_length: body.length, notice: selected.notice, draft_revision: 0,
        tasks: selected.tasks.map(publicTask), attempts: [], drafts: Object.fromEntries(selected.tasks.map((task) => [task.id, { answer: '', active_seconds: 0 }])),
        help: Object.fromEntries(selected.tasks.map((task) => [task.id, { hints: [], solution: null }])),
        summary: { total: 0, answered: 0, independent_total: 0, independent_correct: 0, assisted: 0, corrections: 0, skipped: 0, active_seconds: 0 },
        options: copy(body),
      };
      session.summary = summary(session);
      await tx.objectStore('sessions').add({ id, owner: device.owner, origin: 'device', schema: 1,
        course_revision: this.course.package_revision, session, materials: selected.tasks, familiar_task_ids: selected.familiar }, id);
      for (const task of selected.tasks) {
        const exposureKey = `${device.owner}:${task.instance_key}`;
        const previous = await tx.objectStore('exposures').get(exposureKey);
        await tx.objectStore('exposures').put({ ...previous, owner: device.owner,
          instance_key: task.instance_key, last_seen: now }, exposureKey);
      }
      await tx.objectStore('meta').put({ ...device, active_session_id: id }, 'device');
      return session;
    });
  }

  session(id: string): Promise<LearningSession> {
    return this.repository.read(async (tx, device) => {
      const record = await tx.objectStore('sessions').get(id);
      if (!record) throw new OfflineError('session_not_found', 'Занятие не найдено на этом устройстве. Серверная история хранится отдельно.');
      return owned(record, device.owner).session;
    });
  }

  draft(id: string, body: DraftBody): Promise<{ draft_revision: number }> {
    return this.repository.write(async (tx, device) => {
      const record = await this.active(tx, device.owner, id);
      this.task(record, body.task_id);
      if (Object.keys(body).some((name) => !['task_id', 'answer', 'active_seconds', 'expected_revision'].includes(name))
        || typeof body.answer !== 'string' || Array.from(body.answer).length > 64
        || !Number.isSafeInteger(body.expected_revision) || body.expected_revision < 0) {
        throw new OfflineError('invalid_draft', 'Черновик должен содержать не более 64 символов и действующую редакцию.');
      }
      const current = record.session.drafts[body.task_id];
      const activeSeconds = Math.max(current.active_seconds, boundedSeconds(body.active_seconds));
      if (current.answer === body.answer && current.active_seconds === activeSeconds) return { draft_revision: record.session.draft_revision };
      if (body.expected_revision !== record.session.draft_revision) {
        throw new OfflineError('draft_conflict', 'Черновик уже изменён в другом окне. Прочитайте занятие заново; исходный ввод не удалялся.');
      }
      record.session.drafts[body.task_id] = { answer: body.answer, active_seconds: activeSeconds };
      record.session.draft_revision++;
      record.session.summary = summary(record.session);
      await tx.objectStore('sessions').put(record, record.id);
      return { draft_revision: record.session.draft_revision };
    });
  }

  position(id: string, index: number): Promise<LearningSession> {
    return this.repository.write(async (tx, device) => {
      const record = await this.active(tx, device.owner, id);
      if (!Number.isSafeInteger(index) || index < 0 || index >= record.session.tasks.length) {
        throw new OfflineError('invalid_position', 'Выберите задачу из текущего занятия.');
      }
      record.session.current_index = index;
      await tx.objectStore('sessions').put(record, record.id);
      return record.session;
    });
  }

  attempt(id: string, body: AttemptBody, key: string): Promise<Attempt> {
    return this.operation(`attempt:${id}`, key, body, async (tx, device) => {
      const record = await this.active(tx, device.owner, id);
      const task = this.task(record, body.task_id);
      if (Object.keys(body).some((name) => !['task_id', 'answer', 'active_seconds', 'skipped'].includes(name))
        || typeof body.skipped !== 'boolean' || typeof body.answer !== 'string') {
        throw new OfflineError('invalid_request', 'Неверный формат попытки.');
      }
      boundedSeconds(body.active_seconds);
      if (body.skipped && body.answer !== '') throw new OfflineError('invalid_skip', 'При пропуске ответ должен быть пустым.', 'answer');
      const checked = body.skipped ? null : checkAnswer(body.answer, task.answer);
      const exposure = await this.exposure(tx, device.owner, task.instance_key);
      const first = !record.session.attempts.some((attempt) => attempt.task_id === task.id);
      const helped = record.session.help[task.id];
      const assisted = Boolean(exposure.assistance_seen || exposure.reference_seen || helped.hints.length || helped.solution);
      const draft = record.session.drafts[task.id];
      const activeSeconds = Math.max(draft.active_seconds, body.active_seconds);
      const result: Attempt = { id: uuid(), task_id: task.id, raw_answer: body.answer,
        normalized_answer: checked?.normalized_answer ?? null, correct: checked?.correct ?? false,
        assisted, first_attempt: first, independent: !body.skipped && first && !assisted
          && !record.familiar_task_ids.includes(task.id) && !exposure.numeric_attempted,
        skipped: body.skipped, active_seconds: activeSeconds, created_at: new Date(Date.now()).toISOString(),
        expected_answer: parseAnswer(task.answer, 'exam').normalized_answer, solution: copy(task.solution) };
      record.session.attempts.push(result);
      if (draft.active_seconds !== activeSeconds || (!body.skipped && draft.answer !== body.answer)) {
        record.session.drafts[task.id] = { answer: body.skipped ? draft.answer : body.answer, active_seconds: activeSeconds };
        record.session.draft_revision++;
      }
      record.session.summary = summary(record.session);
      await tx.objectStore('sessions').put(record, record.id);
      await tx.objectStore('exposures').put({ ...exposure, reference_seen: true,
        numeric_attempted: exposure.numeric_attempted || !body.skipped }, `${device.owner}:${task.instance_key}`);
      return result;
    });
  }

  private help<T>(id: string, taskId: string, action: (record: SessionRecord, task: OfflineTask) => T): Promise<T> {
    return this.repository.write(async (tx, device) => {
      const record = await this.active(tx, device.owner, id);
      const task = this.task(record, taskId);
      const result = action(record, task);
      const exposure = await this.exposure(tx, device.owner, task.instance_key);
      await tx.objectStore('sessions').put(record, record.id);
      await tx.objectStore('exposures').put({ ...exposure, assistance_seen: true,
        reference_seen: exposure.reference_seen || Boolean(record.session.help[taskId].solution) }, `${device.owner}:${task.instance_key}`);
      return result;
    });
  }

  hint(id: string, taskId: string, level: 1 | 2 | 3): Promise<Hint> {
    return this.help(id, taskId, (record, task) => {
      const state = record.session.help[taskId];
      if (![1, 2, 3].includes(level) || (level > 1 && !state.hints.some((hint) => hint.level === level - 1))) {
        throw new OfflineError('hint_order', 'Подсказки открываются по очереди: сначала первая, затем вторая и третья.');
      }
      const existing = state.hints.find((hint) => hint.level === level);
      if (existing) return existing;
      const result = { level, text: task.hints[level - 1] };
      state.hints.push(result);
      return result;
    });
  }

  solution(id: string, taskId: string): Promise<Solution> {
    return this.help(id, taskId, (record, task) => {
      const state = record.session.help[taskId];
      if (!state.solution) state.solution = { answer: parseAnswer(task.answer, 'exam').normalized_answer, steps: copy(task.solution) };
      return state.solution;
    });
  }

  finish(id: string, key: string): Promise<LearningSession> {
    return this.operation(`finish:${id}`, key, { session_id: id }, async (tx, device) => {
      const record = await tx.objectStore('sessions').get(id);
      if (!record) throw new OfflineError('session_not_found', 'Занятие не найдено на этом устройстве.');
      owned(record, device.owner);
      if (record.session.status === 'completed') return record.session;
      record.session.summary = summary(record.session);
      record.session.status = 'completed';
      record.session.completed_at = new Date(Date.now()).toISOString();
      await tx.objectStore('sessions').put(record, record.id);
      if (device.active_session_id === id) {
        const active = (await tx.objectStore('sessions').getAll()).map((item) => owned(item, device.owner))
          .filter((item) => item.session.status === 'active')
          .sort((a, b) => b.session.created_at.localeCompare(a.session.created_at));
        await tx.objectStore('meta').put({ ...device, active_session_id: active[0]?.id ?? null }, 'device');
      }
      return record.session;
    });
  }

  async progress() {
    const state = await this.state();
    return localProgress(this.course, state.sessions, state.active_session_id);
  }

  close() { return this.repository.close(); }
}
