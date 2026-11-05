import { normalizeEmail } from '../accounts/validation';
import type {
  Attempt, ExportAccount, ExportAnnotation, ExportAssessment, ExportAssessmentResult, ExportAssessmentRow,
  ExportCorrection, ExportDraftAnswer, ExportFigure, ExportFirstDraft, ExportLearning, ExportLearningSession,
  ExportPublicTask, ExportReview, ExportSessionOptions, Hint, HistoryExport, ProfileSource, Skill,
  SlotSource, Solution, Summary,
} from './types';

type Parser<T> = (value: unknown) => T;
type ObjectValue = Record<string, unknown>;

// These are whole-document safety budgets, not pagination or history-count caps.
// Every accepted history entry is retained; exceeding a budget rejects the file.
const MAX_NODES = 2_000_000;
const MAX_DEPTH = 16;
const MAX_TEXT_UNITS = 64 * 1024 * 1024;
const MAX_STRING_UNITS = 1024 * 1024;
const reservedKeys = new Set(['__proto__', 'prototype', 'constructor']);

function invalid(): never { throw new TypeError('Invalid complete history export.'); }

function plainObject(value: unknown): ObjectValue {
  if (!value || typeof value !== 'object' || Array.isArray(value)
    || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return invalid();
  return value as ObjectValue;
}

/** Bound unknown JSON before traversing any DTO, including rejected extra fields. */
function boundedJson(payload: unknown): void {
  let remainingNodes = MAX_NODES;
  let remainingText = MAX_TEXT_UNITS;
  function chargeText(value: string) {
    remainingText -= value.length;
    if (value.length > MAX_STRING_UNITS || remainingText < 0) return invalid();
  }
  function visit(value: unknown, depth: number): void {
    if (--remainingNodes < 0 || depth > MAX_DEPTH) return invalid();
    if (typeof value === 'string') { chargeText(value); return; }
    if (value === null || typeof value === 'boolean') return;
    if (typeof value === 'number') {
      if (!Number.isFinite(value)) return invalid();
      return;
    }
    if (Array.isArray(value)) {
      if (value.length > remainingNodes || Reflect.ownKeys(value).length !== value.length + 1) return invalid();
      for (let index = 0; index < value.length; index++) {
        const descriptor = Object.getOwnPropertyDescriptor(value, index);
        if (!descriptor?.enumerable || !('value' in descriptor)) return invalid();
        visit(descriptor.value, depth + 1);
      }
      return;
    }
    const row = plainObject(value);
    const keys = Reflect.ownKeys(row);
    if (keys.length > remainingNodes) return invalid();
    for (const key of keys) {
      if (typeof key !== 'string' || reservedKeys.has(key)) return invalid();
      chargeText(key);
      const descriptor = Object.getOwnPropertyDescriptor(row, key);
      if (!descriptor?.enumerable || !('value' in descriptor)) return invalid();
      visit(descriptor.value, depth + 1);
    }
  }
  visit(payload, 0);
}

function record<T>(fields: { [K in keyof T]-?: Parser<T[K]> }): Parser<T> {
  const keys = Object.keys(fields) as (keyof T & string)[];
  return (value) => {
    const row = plainObject(value);
    // Reject extras (including auth and grading internals), not merely strip them.
    if (Object.keys(row).length !== keys.length || keys.some((key) => !Object.hasOwn(row, key))) return invalid();
    return Object.fromEntries(keys.map((key) => [key, fields[key](row[key])])) as T;
  };
}

function checked<T>(parse: Parser<T>, valid: (value: T) => boolean): Parser<T> {
  return (value) => {
    const result = parse(value);
    return valid(result) ? result : invalid();
  };
}

function array<T>(parse: Parser<T>, min = 0, max = MAX_NODES): Parser<T[]> {
  return (value) => Array.isArray(value) && value.length >= min && value.length <= max
    ? value.map(parse) : invalid();
}
function nullable<T>(parse: Parser<T>): Parser<T | null> { return (value) => value === null ? null : parse(value); }
function oneOf<const T extends string | number>(...values: T[]): Parser<T> {
  return (value) => values.some((item) => item === value) ? value as T : invalid();
}
function text(min = 0, max = MAX_STRING_UNITS): Parser<string> {
  return (value) => {
    if (typeof value !== 'string') return invalid();
    // Pydantic's string bounds count Unicode characters, not UTF-16 code units.
    const length = [...value].length;
    return length >= min && length <= max ? value : invalid();
  };
}
function integer(min = 0, max = Number.MAX_SAFE_INTEGER): Parser<number> {
  return (value) => typeof value === 'number' && Number.isSafeInteger(value) && value >= min && value <= max ? value : invalid();
}
const flag: Parser<boolean> = (value) => typeof value === 'boolean' ? value : invalid();
const id = checked(text(1, 128), (value) => Boolean(value.trim()) && !reservedKeys.has(value));
const count = integer();
const seconds = integer(0, 86_400);
const answer = text(0, 64);
const slotNumber = integer(1);
const strings = array(text());
const ids = array(id);

function unique<T>(rows: T[], key: (row: T) => string | number): boolean {
  return new Set(rows.map(key)).size === rows.length;
}

function date(value: unknown, dateOnly = false): string {
  const result = text(10, 40)(value);
  const pattern = dateOnly
    ? /^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2}))?$/
    : /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/;
  if (!pattern.test(result) || !Number.isFinite(Date.parse(result))) return invalid();
  const [year, month, day] = result.slice(0, 10).split('-').map(Number);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > days[month - 1]
    || (result.length > 10 && (Number(result.slice(11, 13)) > 23
      || Number(result.slice(14, 16)) > 59 || Number(result.slice(17, 19)) > 59))) return invalid();
  return result;
}
const timestamp: Parser<string> = (value) => date(value);
const sourceDate: Parser<string> = (value) => date(value, true);

const skill = record<Skill>({ id, title: text() });
const sourceSlot = record<SlotSource>({
  number: slotNumber, id, title: text(), level: oneOf('Б', 'П'), summary: text(),
  skills: array(skill, 1), lesson_id: id,
});
const profile = checked(record<ProfileSource>({
  id, year: integer(1, 9999), title: text(), status: oneOf('draft', 'approved'), revision: id,
  verified_at: sourceDate, verification_note: text(), source_urls: strings, slots: array(sourceSlot, 1),
}), (value) => unique(value.slots, (slot) => slot.id) && unique(value.slots, (slot) => slot.number));

const coordinate: Parser<number> = (value) => typeof value === 'number' && Number.isFinite(value)
  && Math.abs(value) <= 10_000 ? value : invalid();
const point = record<{ x: number; y: number }>({ x: coordinate, y: coordinate });
const figure = checked(record<ExportFigure>({
  description: text(1, 2000), x_min: coordinate, x_max: coordinate, y_min: coordinate, y_max: coordinate, axes: flag,
  lines: array(record<ExportFigure['lines'][number]>({ points: array(point, 2, 201), dashed: flag }), 0, 32),
  circles: array(record<ExportFigure['circles'][number]>({
    center: point, radius: checked(coordinate, (value) => value > 0),
  }), 0, 16),
  labels: array(record<ExportFigure['labels'][number]>({ x: coordinate, y: coordinate, text: text(1, 100) }), 0, 48),
}), (value) => value.x_min < value.x_max && value.y_min < value.y_max);
const table = checked(record<NonNullable<ExportPublicTask['table']>>({
  headers: array(text(), 1), rows: array(array(text()), 1),
}), (value) => value.rows.every((row) => row.length === value.headers.length));
const rounding = record<NonNullable<ExportPublicTask['rounding']>>({
  digits: integer(0, 10), mode: oneOf('half_up', 'floor', 'ceil'), instruction: text(1, 300),
});
const task = record<ExportPublicTask>({
  id, revision: id, slot: slotNumber, topic: text(), title: text(), statement: text(), formula: nullable(text()),
  table: nullable(table), skill_ids: array(id, 1), family_id: id, estimated_seconds: integer(1, 86_400),
  review_status: oneOf('demo', 'reviewed'), hint_count: integer(0, 3), slot_id: nullable(id),
  figure: nullable(figure), rounding: nullable(rounding),
});
const draft = record<ExportDraftAnswer>({ answer, active_seconds: seconds });
const hint = record<Hint>({ level: integer(1, 3), text: text() });
const solution = record<Solution>({ answer: text(), steps: strings });
const help = record<ExportLearningSession['help'][string]>({ hints: array(hint, 0, 3), solution: nullable(solution) });

function dictionary<T>(parse: Parser<T>): Parser<Record<string, T>> {
  return (value) => Object.fromEntries(Object.entries(plainObject(value)).map(([key, item]) => [id(key), parse(item)]));
}

const attempt = record<Attempt>({
  id, task_id: id, raw_answer: answer, normalized_answer: nullable(text()), correct: flag, assisted: flag,
  first_attempt: flag, independent: flag, skipped: flag, active_seconds: seconds, created_at: timestamp,
  expected_answer: text(), solution: strings,
});
const summary = checked(record<Summary>({
  total: count, answered: count, independent_total: count, independent_correct: count, assisted: count,
  corrections: count, skipped: count, active_seconds: count,
}), (value) => value.answered <= value.total && value.skipped <= value.total
  && value.independent_correct <= value.independent_total);
const options = record<ExportSessionOptions>({
  slots: checked(array(slotNumber, 1, 100), (value) => unique(value, (item) => item)),
  length: oneOf(5, 10, 20), mode: oneOf('practice'),
  skill_ids: checked(array(id, 0, 100), (value) => unique(value, (item) => item)),
  family_ids: checked(array(id, 0, 100), (value) => unique(value, (item) => item)),
  difficulty: nullable(oneOf(1, 2, 3)), selection: oneOf('balanced', 'mixed'), repeat_task_id: nullable(id),
  until_stopped: flag, target_minutes: nullable(oneOf(10, 20, 30)),
});

function frozenProfile(value: { profile_id: string; profile_revision: string; profile: ProfileSource; tasks: ExportPublicTask[] }): boolean {
  const slots = new Map(value.profile.slots.map((slot) => [slot.number, slot]));
  return value.profile.id === value.profile_id && value.profile.revision === value.profile_revision
    && unique(value.tasks, (task) => task.id)
    && value.tasks.every((task) => {
      const slot = slots.get(task.slot);
      return slot !== undefined && (task.slot_id === null || task.slot_id === slot.id);
    });
}

const session = checked(record<ExportLearningSession>({
  id, profile_id: id, profile_revision: id, profile, mode: oneOf('practice'), status: oneOf('active', 'completed'),
  created_at: timestamp, completed_at: nullable(timestamp), current_index: count, requested_length: oneOf(5, 10, 20),
  notice: nullable(text()), draft_revision: count, tasks: array(task, 1), attempts: array(attempt),
  drafts: dictionary(draft), help: dictionary(help), summary, options: nullable(options),
}), (value) => {
  const taskIds = new Set(value.tasks.map((task) => task.id));
  return frozenProfile(value) && value.current_index <= value.tasks.length && value.summary.total === value.tasks.length
    && ((value.status === 'active') === (value.completed_at === null))
    && unique(value.attempts, (attempt) => attempt.id)
    && value.attempts.every((attempt) => taskIds.has(attempt.task_id))
    && Object.keys(value.drafts).every((key) => taskIds.has(key))
    && Object.keys(value.help).every((key) => taskIds.has(key));
});

const firstDraft = record<ExportFirstDraft>({ answer, active_seconds: seconds, recorded_at: timestamp });
const resultRow = record<ExportAssessmentRow>({
  id, task_id: id, task_revision: id, slot: slotNumber, slot_id: id, family_id: id, skill_ids: array(id, 1),
  raw: answer, normalized: nullable(text()), expected: text(), correct: flag, skipped: flag,
  format_error: flag, format_message: nullable(text()), independent: flag, assisted: flag, first_attempt: flag,
  active_seconds: seconds, solution: strings, first_draft: nullable(firstDraft), first_answer: nullable(firstDraft),
  label: oneOf('Верно', 'Неверно', 'Пропущено', 'Ошибка формата'),
});
const result = checked(record<ExportAssessmentResult>({
  source: oneOf('server', 'local'), reason: oneOf('finished', 'deadline', 'connection_lost'), label: text(),
  score: integer(0, 13), total: oneOf(13), answered: integer(0, 13), skipped: integer(0, 13), format_errors: integer(0, 13),
  independent_total: integer(0, 13), independent_correct: integer(0, 13), assisted_total: integer(0, 13),
  active_seconds: integer(0, 13 * 86_400), elapsed_seconds: count, snapshot_at: timestamp,
  snapshot_hash: checked(text(64, 64), (value) => /^[a-f0-9]{64}$/.test(value)), connection_lost: flag,
  checker_revision: id, rows: array(resultRow, 13, 13), weak_skill_ids: ids, recommendation: text(),
}), (value) => unique(value.rows, (row) => row.id) && unique(value.rows, (row) => row.task_id)
  && value.score === value.rows.filter((row) => row.correct).length
  && value.answered === value.rows.filter((row) => row.normalized !== null).length
  && value.skipped === value.rows.filter((row) => row.skipped).length
  && value.format_errors === value.rows.filter((row) => row.format_error).length
  && value.independent_total === value.rows.filter((row) => row.independent).length
  && value.independent_correct === value.rows.filter((row) => row.independent && row.correct).length
  && value.assisted_total === value.rows.filter((row) => row.assisted).length
  && value.active_seconds === value.rows.reduce((total, row) => total + row.active_seconds, 0));

function releasedResult(value: ExportAssessment, result: ExportAssessmentResult | null, source: 'server' | 'local'): boolean {
  if (result === null) return true;
  // A completed label alone is not release authorization.
  if (value.status !== 'completed' || value.released_at === null || result.source !== source
    || Date.parse(result.snapshot_at) > Date.parse(value.released_at)) return false;
  const tasks = new Map(value.tasks.map((task) => [task.id, task]));
  const slots = new Map(value.profile.slots.map((slot) => [slot.number, slot.id]));
  return result.rows.every((row) => {
    const task = tasks.get(row.task_id);
    return task !== undefined && row.task_revision === task.revision && row.slot === task.slot
      && row.slot_id === slots.get(row.slot) && row.family_id === task.family_id
      && row.skill_ids.length === task.skill_ids.length && row.skill_ids.every((id, index) => id === task.skill_ids[index]);
  });
}

const assessment = checked(record<ExportAssessment>({
  id, mode: oneOf('diagnostic', 'exam'), status: oneOf('prepared', 'active', 'awaiting_snapshot', 'completed'),
  profile_id: id, profile_revision: id, profile, created_at: timestamp, started_at: nullable(timestamp),
  deadline_at: nullable(timestamp), released_at: nullable(timestamp), duration_minutes: integer(15, 180),
  tasks: array(task, 13, 13), drafts: dictionary(draft), server_result: nullable(result), local_result: nullable(result),
  result_notice: text(),
}), (value) => frozenProfile(value) && unique(value.tasks, (task) => task.slot)
  && value.tasks.every((task) => task.slot <= 13 && task.hint_count === 0)
  && Object.keys(value.drafts).every((key) => value.tasks.some((task) => task.id === key))
  && (value.status === 'completed' || value.released_at === null)
  && releasedResult(value, value.server_result, 'server') && releasedResult(value, value.local_result, 'local'));

const annotation = checked(record<ExportAnnotation>({
  id, session_id: id, task_id: id, favourite: flag, manual: flag, not_understood: flag,
  cause: nullable(oneOf('theory', 'model', 'calculation', 'restriction', 'graph', 'format')),
  created_at: timestamp, updated_at: timestamp,
}), (value) => Date.parse(value.created_at) <= Date.parse(value.updated_at));
const review = checked(record<ExportReview>({
  skill_id: id, family_id: id, slot_id: id, due_at: nullable(timestamp), interval_days: count,
  closed: flag, anchor_task_id: id, anchor_at: timestamp,
}), (value) => value.closed === (value.due_at === null));
const correction = record<ExportCorrection>({
  task_id: id, task_revision: id, reason: text(), created_at: timestamp,
  attempt_ids: ids, session_ids: ids, assessment_ids: ids,
});
const learning = record<ExportLearning>({
  algorithm_version: id, annotations: array(annotation), reviews: array(review), corrections: array(correction),
});
const email: Parser<string> = (value) => {
  const result = text(3, 254)(value);
  try { if (normalizeEmail(result) !== result) return invalid(); }
  catch { return invalid(); }
  return result;
};
const deletion = checked(record<NonNullable<ExportAccount['deletion_request']>>({
  id, status: oneOf('requested'), requested_at: timestamp, deadline_at: timestamp,
}), (value) => {
  const interval = Date.parse(value.deadline_at) - Date.parse(value.requested_at);
  return interval >= 0 && interval <= 30 * 24 * 60 * 60 * 1000;
});
const account = record<ExportAccount>({
  id, email, created_at: timestamp, email_verified_at: timestamp, role: oneOf('student', 'methodist', 'admin'),
  daily_minutes: oneOf(10, 20, 30),
  consents: array(record<ExportAccount['consents'][number]>({ policy_version: text(1, 64), accepted_at: timestamp })),
  deletion_request: nullable(deletion),
});
const history = checked(record<HistoryExport>({
  version: oneOf('1'), exported_at: timestamp, profile_id: id, sessions: array(session),
  assessments: array(assessment), learning, account: nullable(account),
}), (value) => unique(value.sessions, (session) => session.id) && unique(value.assessments, (assessment) => assessment.id)
  && unique(value.learning.annotations, (annotation) => annotation.id)
  && unique(value.learning.annotations, (annotation) => JSON.stringify([annotation.session_id, annotation.task_id]))
  && value.assessments.every((assessment) => assessment.released_at === null
    || Date.parse(assessment.released_at) <= Date.parse(value.exported_at)));

/** Fresh, exact public DTO copies only. No pagination, coercion, fallback, or truncation. */
export function parseHistoryExport(payload: unknown): HistoryExport {
  boundedJson(payload);
  return history(payload);
}
