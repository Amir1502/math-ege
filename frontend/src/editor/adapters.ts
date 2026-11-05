import type {
  BaseItem, BaseList, Capability, CheckResult, EditorFigure, EditorMeta, EditorProfile, Evidence,
  JsonObject, JsonValue, Kind, Preview, PreviewLesson, PreviewTask, Revision, RevisionList,
  RevisionSummary, Status, TemplateSample, Withdrawal, WorkedExample,
} from './types';

export class EditorError extends Error {
  constructor(
    message: string, readonly code = 'invalid_response', readonly status = 0,
    readonly field: string | null = null, readonly uncertain = false,
  ) { super(message); this.name = 'EditorError'; }
}

function invalid(): never {
  throw new EditorError('Сервер вернул неполные данные. Повторите запрос.', 'invalid_response', 0, null, true);
}
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return invalid();
  return value as Record<string, unknown>;
}
function text(value: unknown): string { return typeof value === 'string' ? value : invalid(); }
function nullableText(value: unknown): string | null { return value == null ? null : text(value); }
function number(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : invalid();
}
function integer(value: unknown): number { const result = number(value); return Number.isSafeInteger(result) ? result : invalid(); }
function count(value: unknown, minimum = 0, maximum = Number.MAX_SAFE_INTEGER): number {
  const result = integer(value);
  return result >= minimum && result <= maximum ? result : invalid();
}
function bool(value: unknown): boolean { return typeof value === 'boolean' ? value : invalid(); }
function array<T>(value: unknown, decode: (item: unknown) => T): T[] {
  return Array.isArray(value) ? value.map(decode) : invalid();
}
function choice<T extends string>(value: unknown, options: readonly T[]): T {
  return typeof value === 'string' && options.includes(value as T) ? value as T : invalid();
}
const kind = (value: unknown): Kind => choice(value, ['task', 'lesson', 'profile', 'template']);
const status = (value: unknown): Status => choice(value, ['draft', 'review', 'ready', 'published', 'archived']);
const capability = (value: unknown): Capability => choice(value, [
  'edit', 'submit', 'return_to_draft', 'approve', 'publish', 'fork', 'archive', 'withdraw', 'run_checks', 'review_sample',
]);

function json(value: unknown, depth = 0): JsonValue {
  if (depth > 20) return invalid();
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') return number(value);
  if (Array.isArray(value)) return value.map(child => json(child, depth + 1));
  const fields = Object.entries(object(value));
  if (fields.some(([key]) => ['__proto__', 'constructor', 'prototype'].includes(key))) return invalid();
  return Object.fromEntries(fields.map(([key, child]) => [key, json(child, depth + 1)]));
}
export function jsonObject(value: unknown): JsonObject { object(value); return json(value) as JsonObject; }
export function strings(value: unknown): string[] { return array(value, text); }

export function decodeProfile(value: unknown): EditorProfile {
  const v = object(value);
  return {
    id: text(v.id), title: text(v.title), year: integer(v.year), status: choice(v.status, ['draft', 'approved']),
    ...(v.revision === undefined ? {} : { revision: text(v.revision) }),
    verified_at: text(v.verified_at), verification_note: text(v.verification_note), source_urls: strings(v.source_urls),
    slots: array(v.slots, value => { const slot = object(value); return {
      id: text(slot.id), number: integer(slot.number), title: text(slot.title), level: choice(slot.level, ['Б', 'П']),
      summary: text(slot.summary), lesson_id: text(slot.lesson_id),
      skills: array(slot.skills, value => { const skill = object(value); return { id: text(skill.id), title: text(skill.title) }; }),
    }; }),
  };
}

export function decodeMeta(value: unknown): EditorMeta {
  const v = object(value); const actor = object(v.actor);
  return {
    actor: { id: text(actor.id), role: choice(actor.role, ['methodist', 'admin']), owner_id: text(actor.owner_id) },
    profile: decodeProfile(v.profile), kinds: array(v.kinds, kind), statuses: array(v.statuses, status),
    max_import_items: count(v.max_import_items, 1, 10), max_request_bytes: count(v.max_request_bytes, 1),
    templates: array(v.templates, value => { const t = object(value); return {
      id: text(t.id), title: text(t.title), slot: integer(t.slot), skill_ids: strings(t.skill_ids),
    }; }),
  };
}

function decodeSummary(value: unknown): RevisionSummary {
  const v = object(value);
  return {
    id: text(v.id), kind: kind(v.kind), content_id: text(v.content_id), content_revision: text(v.content_revision),
    title: text(v.title), version: count(v.version, 1), revision: count(v.revision, 1), status: status(v.status),
    author_id: text(v.author_id), reviewer_id: nullableText(v.reviewer_id), change_note: text(v.change_note),
    created_at: text(v.created_at), updated_at: text(v.updated_at), capabilities: array(v.capabilities, capability),
  };
}
function decodeEvidence(value: unknown): Evidence {
  const v = object(value);
  return {
    automated_seeds: count(v.automated_seeds), automated_passed: bool(v.automated_passed),
    reviewed_seeds: array(v.reviewed_seeds, seed => count(seed, 0, 4_294_967_295)),
    rejected_seeds: array(v.rejected_seeds, seed => count(seed, 0, 4_294_967_295)),
    checks: strings(v.checks), failure: nullableText(v.failure),
  };
}
export function decodeRevision(value: unknown): Revision {
  const v = object(value);
  return {
    ...decodeSummary(v), payload: jsonObject(v.payload), review_note: nullableText(v.review_note),
    published_at: nullableText(v.published_at), evidence: v.evidence == null ? null : decodeEvidence(v.evidence),
    audit: array(v.audit, value => { const e = object(value); return {
      id: text(e.id), actor_id: text(e.actor_id), actor_role: text(e.actor_role), action: text(e.action),
      from_status: nullableText(e.from_status), to_status: nullableText(e.to_status), note: text(e.note), created_at: text(e.created_at),
    }; }),
  };
}
export function decodeRevisions(value: unknown): RevisionList {
  const v = object(value);
  return { items: array(v.items, decodeSummary), total: count(v.total), limit: count(v.limit, 1, 100), offset: count(v.offset) };
}
export function decodeBase(value: unknown): BaseList {
  const v = object(value);
  return { total: count(v.total), items: array(v.items, value => {
    const row = object(value);
    return { kind: kind(row.kind), content_id: text(row.content_id), title: text(row.title), content_revision: text(row.content_revision) } satisfies BaseItem;
  }) };
}
export function decodeBatch(value: unknown): Revision[] { return array(object(value).items, decodeRevision); }

function point(value: unknown): { x: number; y: number } { const v = object(value); return { x: number(v.x), y: number(v.y) }; }
function figure(value: unknown): EditorFigure {
  const v = object(value);
  return {
    description: text(v.description), x_min: number(v.x_min), x_max: number(v.x_max),
    y_min: number(v.y_min), y_max: number(v.y_max), axes: bool(v.axes),
    lines: array(v.lines, value => { const line = object(value); return { points: array(line.points, point), dashed: bool(line.dashed) }; }),
    circles: array(v.circles, value => { const circle = object(value); return { center: point(circle.center), radius: number(circle.radius) }; }),
    labels: array(v.labels, value => ({ ...point(value), text: text(object(value).text) })),
  };
}
export function decodeTask(value: unknown): PreviewTask {
  const v = object(value);
  const table = v.table == null ? null : object(v.table);
  const rounding = v.rounding == null ? null : object(v.rounding);
  // Deliberate field allowlist: private answers never become TaskContent props.
  return {
    id: text(v.id), revision: text(v.revision), slot: integer(v.slot), slot_id: nullableText(v.slot_id),
    topic: text(v.topic), title: text(v.title), statement: text(v.statement), formula: nullableText(v.formula),
    table: table ? { headers: strings(table.headers), rows: array(table.rows, strings) } : null,
    skill_ids: strings(v.skill_ids), family_id: text(v.family_id), estimated_seconds: integer(v.estimated_seconds),
    review_status: choice(v.review_status, ['demo', 'reviewed']), hint_count: integer(v.hint_count),
    figure: v.figure == null ? null : figure(v.figure),
    rounding: rounding ? { digits: integer(rounding.digits), mode: choice(rounding.mode, ['half_up', 'floor', 'ceil']), instruction: text(rounding.instruction) } : null,
  };
}
function example(value: unknown): WorkedExample {
  const v = object(value); return { statement: text(v.statement), steps: strings(v.steps), answer: text(v.answer) };
}
export function decodeLesson(value: unknown): PreviewLesson {
  const v = object(value);
  return { title: text(v.title), sections: array(v.sections, value => { const s = object(value); return {
    heading: text(s.heading), body: text(s.body), formula: nullableText(s.formula),
  }; }), example: example(v.example), examples: array(v.examples ?? [], example), takeaway: text(v.takeaway) };
}
export function decodePreview(value: unknown): Preview {
  const v = object(value);
  const type = kind(v.kind); const payload = jsonObject(v.payload);
  const task = v.task == null ? null : decodeTask(v.task);
  if (type === 'task') {
    if (!task) return invalid();
    text(payload.answer); strings(payload.hints); strings(payload.solution);
  } else if (type === 'lesson') decodeLesson(payload);
  else if (type === 'profile') decodeProfile(payload);
  else { text(payload.title); text(payload.generator_id); text(payload.generator_version); text(payload.slot_id); text(payload.formula_notes); strings(payload.constraints); }
  return { kind: type, payload, message: text(v.message), task };
}
export function decodeSample(value: unknown): TemplateSample {
  const v = object(value); const task = object(v.task);
  const outputHash = text(v.output_hash);
  if (!/^[0-9a-f]{64}$/.test(outputHash)) return invalid();
  return { seed: count(v.seed, 0, 4_294_967_295), output_hash: outputHash, task: decodeTask(task),
    answer: text(task.answer), hints: strings(task.hints), solution: strings(task.solution) };
}
export function decodeCheck(value: unknown): CheckResult {
  const v = object(value);
  return { id: text(v.id), passed: bool(v.passed), seed_count: count(v.seed_count), checks: strings(v.checks), failure: nullableText(v.failure) };
}
export function decodeWithdrawal(value: unknown): Withdrawal {
  const v = object(value);
  if (v.historical_scores_unchanged !== true) return invalid();
  return {
    task_id: text(v.task_id), task_revision: text(v.task_revision), reason: text(v.reason),
    created_at: text(v.created_at), historical_scores_unchanged: true,
  };
}

export function errorText(error: unknown): string {
  return error instanceof EditorError ? error.message : 'Не удалось связаться с редактором. Проверьте сеть и повторите запрос.';
}
