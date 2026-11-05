import { ApiError, request } from '../api/client';
import type { Attempt, Figure, PublicTask, Summary } from '../api/types';
import type {
  AnnotationBody, AssessmentHistory, DashboardCollection, ErrorCause, LearningDashboard, LearningExtrasApi,
  MasteryStatus, OriginalProfile, PlanMinutes, PracticeProgress, SavedAnnotation, SlotEvidence, TimePlan,
} from './types';

type ObjectValue = Record<string, unknown>;
type Transport = (path: string, method?: string, body?: unknown, key?: string) => Promise<unknown>;

const statuses: readonly MasteryStatus[] = ['Нет данных', 'Изучаю', 'Закрепляю', 'Освоено'];
export const errorCauses: readonly ErrorCause[] = ['theory', 'model', 'calculation', 'restriction', 'graph', 'format'];

function invalid(): never {
  throw new ApiError(502, 'invalid_learning_response', 'Не удалось прочитать учебные данные. Повторите загрузку.');
}

function object(value: unknown): ObjectValue {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return invalid();
  return value as ObjectValue;
}
function text(value: unknown): string { return typeof value === 'string' ? value : invalid(); }
function id(value: unknown): string { const result = text(value); return result.trim() ? result : invalid(); }
function nullableText(value: unknown): string | null { return value == null ? null : text(value); }
function count(value: unknown): number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : invalid();
}
function flag(value: unknown): boolean { return typeof value === 'boolean' ? value : invalid(); }
function list(value: unknown): unknown[] { return Array.isArray(value) ? value : invalid(); }
function texts(value: unknown): string[] { return list(value).map(text); }
function date(value: unknown): string {
  const result = text(value);
  return Number.isFinite(Date.parse(result)) ? result : invalid();
}
function slotNumber(value: unknown): number {
  const number = count(value);
  return number >= 1 && number <= 13 ? number : invalid();
}
function mastery(value: unknown): MasteryStatus {
  return statuses.includes(value as MasteryStatus) ? value as MasteryStatus : invalid();
}
function cause(value: unknown): ErrorCause | null {
  if (value === null) return null;
  return errorCauses.includes(value as ErrorCause) ? value as ErrorCause : invalid();
}
function evidence(value: ObjectValue) {
  const attempts = count(value.attempts);
  const correct = count(value.correct);
  if (correct > attempts) return invalid();
  return { attempts, correct };
}
function independentEvidence(value: ObjectValue) {
  const independent_total = count(value.independent_total);
  const independent_correct = count(value.independent_correct);
  if (independent_correct > independent_total) return invalid();
  return { independent_total, independent_correct };
}
function coverage(value: ObjectValue) {
  const covered_skills = count(value.covered_skills);
  const total_skills = count(value.total_skills);
  if (covered_skills > total_skills) return invalid();
  return { covered_skills, total_skills };
}

function coordinate(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= 10_000 ? value : invalid();
}
function point(value: unknown) {
  const row = object(value);
  return { x: coordinate(row.x), y: coordinate(row.y) };
}
function figure(value: unknown): Figure | null {
  if (value == null) return null;
  const row = object(value);
  const bounds = { x_min: coordinate(row.x_min), x_max: coordinate(row.x_max), y_min: coordinate(row.y_min), y_max: coordinate(row.y_max) };
  if (bounds.x_min >= bounds.x_max || bounds.y_min >= bounds.y_max) return invalid();
  return {
    description: text(row.description), ...bounds, axes: flag(row.axes),
    lines: list(row.lines).map((value) => {
      const line = object(value);
      return { points: list(line.points).map(point), dashed: flag(line.dashed) };
    }),
    circles: list(row.circles).map((value) => {
      const circle = object(value);
      const radius = coordinate(circle.radius);
      if (radius <= 0) return invalid();
      return { center: point(circle.center), radius };
    }),
    labels: list(row.labels).map((value) => ({ ...point(value), text: text(object(value).text) })),
  };
}
function rounding(value: unknown): PublicTask['rounding'] {
  if (value == null) return null;
  const row = object(value);
  if (!['half_up', 'floor', 'ceil'].includes(text(row.mode)) || count(row.digits) > 10) return invalid();
  return { digits: count(row.digits), mode: row.mode as 'half_up' | 'floor' | 'ceil', instruction: text(row.instruction) };
}

/** Copy public condition fields only: unknown answer/help fields never enter a cache. */
function task(value: unknown): PublicTask {
  const row = object(value);
  const table = row.table === null ? null : object(row.table);
  if (row.review_status !== 'demo' && row.review_status !== 'reviewed') return invalid();
  return {
    id: id(row.id), revision: id(row.revision), slot: slotNumber(row.slot),
    topic: text(row.topic), title: text(row.title), statement: text(row.statement),
    formula: nullableText(row.formula),
    table: table ? { headers: texts(table.headers), rows: list(table.rows).map(texts) } : null,
    skill_ids: texts(row.skill_ids), family_id: id(row.family_id),
    estimated_seconds: count(row.estimated_seconds), review_status: row.review_status,
    hint_count: count(row.hint_count), slot_id: nullableText(row.slot_id), figure: figure(row.figure), rounding: rounding(row.rounding),
  };
}

function releasedAttempt(value: unknown, taskId: string): Attempt | null {
  if (value === null) return null;
  const row = object(value);
  if (row.task_id !== taskId || row.released === false) return invalid();
  return {
    id: id(row.id), task_id: taskId, raw_answer: text(row.raw_answer),
    normalized_answer: nullableText(row.normalized_answer), correct: flag(row.correct),
    assisted: flag(row.assisted), first_attempt: flag(row.first_attempt),
    independent: flag(row.independent), skipped: flag(row.skipped),
    active_seconds: count(row.active_seconds), created_at: date(row.created_at),
    expected_answer: text(row.expected_answer), solution: texts(row.solution),
  };
}

function profile(value: unknown, fallbackId?: unknown): OriginalProfile {
  if (value == null) return { id: id(fallbackId), title: null, year: null, revision: null };
  const row = object(value);
  return {
    id: id(row.id ?? fallbackId), title: nullableText(row.title),
    year: row.year == null ? null : count(row.year), revision: nullableText(row.revision),
  };
}

function taskProfile(row: ObjectValue): OriginalProfile | null {
  return row.profile_id == null ? null : {
    ...profile(row.original_profile, row.profile_id), revision: id(row.profile_revision),
  };
}

function assessment(value: unknown): AssessmentHistory {
  const row = object(value);
  if (row.released === false || (row.status !== undefined && row.status !== 'completed')
    || !['diagnostic', 'exam'].includes(text(row.mode)) || row.total !== 13) return invalid();
  const score = count(row.score);
  if (score > 13) return invalid();
  return {
    id: id(row.id), mode: row.mode as AssessmentHistory['mode'], released_at: date(row.released_at), snapshot_at: date(row.snapshot_at),
    score, total: 13, answered: count(row.answered), skipped: count(row.skipped), format_errors: count(row.format_errors),
    active_seconds: count(row.active_seconds), elapsed_seconds: count(row.elapsed_seconds),
    profile: { ...profile(row.original_profile, row.profile_id), revision: id(row.profile_revision) },
  };
}

function slot(value: unknown): SlotEvidence {
  const row = object(value);
  return {
    slot_id: id(row.slot_id), number: slotNumber(row.number), title: text(row.title),
    status: mastery(row.status), ...evidence(row), ...coverage(row),
    skills: list(row.skills).map((value) => {
      const skill = object(value);
      return { id: id(skill.id), title: text(skill.title), ...evidence(skill) };
    }),
  };
}

function dashboard(value: unknown): LearningDashboard {
  const row = object(value);
  const page = object(row.pagination);
  const offset = count(page.offset);
  const limit = count(page.limit);
  if (offset > 1_000_000 || limit < 1 || limit > 100) return invalid();
  const pageTotals = object(page.totals);
  const totals: Partial<Record<DashboardCollection, number>> = {};
  for (const key of ['reviews', 'weak_skills', 'favourites', 'journal', 'assessment_history', 'notifications'] as const) {
    if (pageTotals[key] !== undefined) totals[key] = count(pageTotals[key]);
  }
  const slots = list(row.slots).map(slot);
  if (new Set(slots.map((item) => item.slot_id)).size !== slots.length
    || new Set(slots.map((item) => item.number)).size !== slots.length) return invalid();
  return {
    algorithm_version: id(row.algorithm_version), notice: nullableText(row.notice), slots,
    ...independentEvidence(row),
    assisted_total: count(row.assisted_total), corrections_total: count(row.corrections_total),
    skipped_total: count(row.skipped_total), excluded_total: count(row.excluded_total),
    reviews: list(row.reviews).map((value) => {
      const item = object(value);
      return {
        skill_id: id(item.skill_id), family_id: id(item.family_id), slot_id: id(item.slot_id),
        slot: item.slot === null ? null : slotNumber(item.slot), due_at: date(item.due_at), interval_days: count(item.interval_days),
        overdue: flag(item.overdue),
      };
    }),
    weak_skills: list(row.weak_skills).map((value) => {
      const item = object(value);
      return { id: id(item.id), title: text(item.title), slot: slotNumber(item.slot), family_ids: texts(item.family_ids) };
    }),
    favourites: list(row.favourites).map((value) => {
      const item = object(value);
      if (item.released === false) return invalid();
      return { task: task(item.task), session_id: id(item.session_id), profile: taskProfile(item) };
    }),
    journal: list(row.journal).map((value) => {
      const item = object(value);
      if (item.released === false || (item.assessment_status !== undefined && item.assessment_status !== 'completed')) return invalid();
      const condition = task(item.task);
      return {
        id: id(item.id), task: condition, session_id: id(item.session_id), profile: taskProfile(item),
        attempt: releasedAttempt(item.attempt, condition.id), cause: cause(item.cause),
        manual: flag(item.manual), not_understood: flag(item.not_understood),
      };
    }),
    assessment_history: list(row.assessment_history).map(assessment),
    notifications: list(row.notifications).map((value) => {
      const item = object(value);
      return { id: id(item.id), message: text(item.message), created_at: date(item.created_at) };
    }),
    recommendation: text(row.recommendation), pagination: { offset, limit, totals },
  };
}

function plan(value: unknown, minutes: PlanMinutes): TimePlan {
  const row = object(value);
  if (row.minutes !== minutes || ![5, 10, 20].includes(count(row.length)) || row.selection !== 'mixed') return invalid();
  const slots = list(row.slots).map(slotNumber);
  if (new Set(slots).size !== slots.length) return invalid();
  return {
    minutes, length: row.length as TimePlan['length'], estimated_seconds: count(row.estimated_seconds),
    slots, selection: 'mixed', notice: nullableText(row.notice),
  };
}

function summary(value: unknown): Summary {
  const row = object(value);
  return {
    total: count(row.total), answered: count(row.answered), ...independentEvidence(row), assisted: count(row.assisted),
    corrections: count(row.corrections), skipped: count(row.skipped), active_seconds: count(row.active_seconds),
  };
}

function progress(value: unknown): PracticeProgress {
  const row = object(value);
  return {
    algorithm_version: id(row.algorithm_version), notice: nullableText(row.notice), excluded_total: count(row.excluded_total),
    ...independentEvidence(row),
    assisted_total: count(row.assisted_total), corrections_total: count(row.corrections_total), skipped_total: count(row.skipped_total),
    active_session_id: nullableText(row.active_session_id), active_assessment_id: nullableText(row.active_assessment_id),
    slots: list(row.slots).map((value) => {
      const item = object(value);
      return { number: slotNumber(item.number), status: mastery(item.status), ...evidence(item), ...coverage(item) };
    }),
    recent_sessions: list(row.recent_sessions).map((value) => {
      const item = object(value);
      if (!['active', 'completed'].includes(text(item.status)) || (item.mode !== undefined && item.mode !== 'practice')) return invalid();
      return {
        id: id(item.id), status: item.status as 'active' | 'completed', created_at: date(item.created_at),
        summary: summary(item.summary),
        profile: item.profile != null || item.original_profile != null || item.profile_id != null
          ? profile(item.profile ?? item.original_profile, item.profile_id) : null,
      };
    }),
  };
}

/** Omitting a field is different from explicitly setting false or clearing a cause. */
export function annotationBody(value: AnnotationBody): AnnotationBody {
  const result: AnnotationBody = { session_id: id(value.session_id), task_id: id(value.task_id) };
  if (value.favourite !== undefined) result.favourite = flag(value.favourite);
  if (value.manual !== undefined) result.manual = flag(value.manual);
  if (value.not_understood !== undefined) result.not_understood = flag(value.not_understood);
  if (value.cause !== undefined) result.cause = cause(value.cause);
  if (Object.keys(result).length === 2) throw new ApiError(422, 'empty_annotation', 'Выберите отметку или причину для сохранения.');
  return result;
}

function savedAnnotation(value: unknown): SavedAnnotation {
  const row = object(value);
  return {
    session_id: id(row.session_id), task_id: id(row.task_id),
    favourite: flag(row.favourite), manual: flag(row.manual), not_understood: flag(row.not_understood), cause: cause(row.cause),
  };
}

/** Dashboard collections have independent offsets; absence there does not mean false. */
async function annotations(transport: Transport, isCurrent: () => boolean): Promise<SavedAnnotation[]> {
  const records: SavedAnnotation[] = [];
  const keys = new Set<string>();
  let offset = 0;
  let total: number | null = null;
  while (isCurrent()) {
    const row = object(await transport(`/learning/export?offset=${offset}&limit=100`));
    if (!isCurrent()) return [];
    const page = object(row.pagination);
    const limit = count(page.limit);
    const currentTotal = count(object(page.totals).annotations);
    if (page.offset !== offset || limit < 1 || limit > 100 || offset > 1_000_000
      || (total !== null && total !== currentTotal)) return invalid();
    total = currentTotal;
    const items = list(row.annotations).map(savedAnnotation);
    if (items.length !== Math.min(limit, Math.max(0, total - offset))) return invalid();
    for (const item of items) {
      const key = JSON.stringify([item.session_id, item.task_id]);
      if (keys.has(key)) return invalid();
      keys.add(key);
      records.push(item);
    }
    offset += limit;
    if (offset >= total) return records;
    if (offset > 1_000_000) return invalid();
  }
  return [];
}

export function createLearningExtrasApi(transport: Transport = request): LearningExtrasApi {
  return {
    dashboard: async (page) => dashboard(await transport(page
      ? `/learning/dashboard?offset=${page.offset}&limit=${page.limit ?? 50}`
      : '/learning/dashboard')),
    plan: async (minutes) => plan(await transport(`/learning/plan?minutes=${minutes}`), minutes),
    progress: async () => progress(await transport('/progress')),
    annotations: (isCurrent = () => true) => annotations(transport, isCurrent),
    annotate: async (body, key) => {
      const saved = savedAnnotation(await transport('/learning/annotations', 'POST', annotationBody(body), key));
      if (saved.session_id !== body.session_id || saved.task_id !== body.task_id) return invalid();
      return saved;
    },
  };
}

export const learningExtrasApi = createLearningExtrasApi();
