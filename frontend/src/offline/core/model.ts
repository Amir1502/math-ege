import type { LearningSession, OfflineTask, PublicTask, Summary } from '../types';

export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function uuid(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0'));
  return [hex.slice(0, 4), hex.slice(4, 6), hex.slice(6, 8), hex.slice(8, 10), hex.slice(10)].map((part) => part.join('')).join('-');
}

export function copy<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export function publicTask(task: OfflineTask): PublicTask {
  return { id: task.id, revision: task.revision, slot: task.slot, slot_id: task.slot_id,
    topic: task.topic, title: task.title, statement: task.statement, formula: task.formula,
    table: task.table, figure: task.figure, rounding: task.rounding, skill_ids: task.skill_ids,
    family_id: task.family_id, estimated_seconds: task.estimated_seconds,
    review_status: task.review_status, hint_count: task.hint_count };
}

export function summary(session: LearningSession): Summary {
  return {
    total: session.tasks.length,
    answered: new Set(session.attempts.filter((item) => !item.skipped).map((item) => item.task_id)).size,
    independent_total: session.attempts.filter((item) => item.independent).length,
    independent_correct: session.attempts.filter((item) => item.independent && item.correct).length,
    assisted: session.attempts.filter((item) => item.assisted && !item.skipped).length,
    corrections: session.attempts.filter((item) => !item.first_attempt && !item.skipped).length,
    skipped: new Set(session.attempts.filter((item) => item.skipped).map((item) => item.task_id)).size,
    active_seconds: Object.values(session.drafts).reduce((total, item) => total + item.active_seconds, 0),
  };
}
