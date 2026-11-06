import { parseAnswer } from '../checker';
import { OfflineError } from '../types';
import type { Figure, Lesson, Profile, PublicTask } from '../../api/types';
import type { OfflineTask } from '../types';

type ObjectValue = Record<string, unknown>;
const MARKUP = /<\s*(?:\/?[A-Za-z][A-Za-z0-9:._-]*(?=[\s/>])[^>]*|!DOCTYPE\b[^>]*|!--.*?)>/isu;
const MATH_COMMANDS = new Set(`frac dfrac tfrac sqrt cdot times div pm mp le leq ge geq ne neq approx equiv sim simeq lt gt in notin subset subseteq supset supseteq cup cap setminus emptyset varnothing infty alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega sin cos tan cot tg ctg sec csc arcsin arccos arctan sinh cosh tanh log ln lg exp min max lim sum prod int iint oint limits nolimits overline underline vec overrightarrow hat bar dot ddot left right middle big Big bigg Bigg bigl bigr Bigl Bigr biggl biggr Biggl Biggr text textrm textnormal textbf textit mathrm mathit mathbf mathbb mathcal mathsf mathtt operatorname displaystyle textstyle scriptstyle scriptscriptstyle begin end quad qquad hspace vspace phantom hphantom vphantom strut ldots cdots vdots ddots dots colon mid vert Vert lvert rvert lVert rVert langle rangle lbrace rbrace lceil rceil lfloor rfloor degree angle triangle parallel perp to rightarrow leftarrow leftrightarrow Rightarrow Leftarrow Leftrightarrow Longrightarrow Longleftrightarrow iff forall exists neg not land lor circ bullet therefore because binom dbinom tbinom underbrace overbrace underset overset substack cases det gcd Pr`.split(' '));
const ENVIRONMENTS = new Set(['aligned', 'gathered', 'array', 'matrix', 'pmatrix', 'bmatrix', 'cases']);
const FORBIDDEN_KEYS = new Set(['__proto__', 'constructor', 'prototype']);
export const HASH = /^[0-9a-f]{64}$/u;

export function invalid(message = 'Неверная структура встроенного курса.'): never {
  throw new OfflineError('invalid_content', message);
}

/** Mirrors the backend data-only boundary, including safe TeX and bounded JSON trees. */
export function safeData(value: unknown, maxNodes = 12_000, maxBytes = 131_072): void {
  let count = 0;
  function walk(item: unknown, depth: number): void {
    if (++count > maxNodes || depth > 16) invalid('Слишком сложная структура встроенного курса.');
    if (typeof item === 'string') {
      if (Array.from(item).length > 16_000 || MARKUP.test(item)) {
        throw new OfflineError('unsafe_content', 'HTML, SVG и слишком длинные строки запрещены.');
      }
      for (const [, command] of item.matchAll(/\\([A-Za-z]+)/gu)) {
        if (!MATH_COMMANDS.has(command)) throw new OfflineError('unsafe_formula', 'Формула содержит неподдерживаемую команду LaTeX.');
      }
      for (const [, environment] of item.matchAll(/\\(?:begin|end)\s*\{([^}]*)\}/gu)) {
        if (!ENVIRONMENTS.has(environment)) throw new OfflineError('unsafe_formula', 'Окружение LaTeX не разрешено.');
      }
    } else if (Array.isArray(item)) {
      if (item.length > 1200) invalid();
      for (const child of item) walk(child, depth + 1);
    } else if (item !== null && typeof item === 'object') {
      for (const [key, child] of Object.entries(item)) {
        if (FORBIDDEN_KEYS.has(key)) invalid();
        walk(child, depth + 1);
      }
    } else if (item !== null && typeof item !== 'boolean' && (typeof item !== 'number' || !Number.isFinite(item))) {
      invalid();
    }
  }
  walk(value, 0);
  if (new TextEncoder().encode(JSON.stringify(value)).byteLength > maxBytes) invalid('Запись встроенного курса слишком велика.');
}

export function object(value: unknown): ObjectValue {
  if (!value || typeof value !== 'object' || Array.isArray(value)) invalid();
  return value as ObjectValue;
}

function keys(value: ObjectValue, allowed: string[]): void {
  if (Object.keys(value).some((key) => !allowed.includes(key))) invalid();
}

export function text(value: unknown, min = 0, max = 16_000): string {
  if (typeof value !== 'string' || Array.from(value).length < min || Array.from(value).length > max) invalid();
  return value;
}

export function identifier(value: unknown): string {
  const id = text(value, 1, 128);
  if (FORBIDDEN_KEYS.has(id)) invalid();
  return id;
}

export function integer(value: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < min || value > max) invalid();
  return value;
}

function coordinate(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || Math.abs(value) > 10_000) invalid();
  return value;
}

function bool(value: unknown): boolean {
  if (typeof value !== 'boolean') invalid();
  return value;
}

export function array(value: unknown, min = 0, max = 1200): unknown[] {
  if (!Array.isArray(value) || value.length < min || value.length > max) invalid();
  return value;
}

function strings(value: unknown, min = 0, ids = false): string[] {
  return array(value, min).map((item) => ids ? identifier(item) : text(item));
}

export function unique<T>(values: T[]): void {
  if (new Set(values).size !== values.length) invalid('Идентификаторы встроенного курса должны быть уникальны.');
}

function choice<T extends string | number>(value: unknown, choices: readonly T[]): T {
  if (!choices.includes(value as T)) invalid();
  return value as T;
}

function point(value: unknown) {
  const raw = object(value);
  keys(raw, ['x', 'y']);
  return { x: coordinate(raw.x), y: coordinate(raw.y) };
}

function figure(value: unknown): Figure | null {
  if (value === null || value === undefined) return null;
  const raw = object(value);
  keys(raw, ['description', 'x_min', 'x_max', 'y_min', 'y_max', 'axes', 'lines', 'circles', 'labels']);
  const parsed: Figure = {
    description: text(raw.description, 1, 2000), x_min: coordinate(raw.x_min), x_max: coordinate(raw.x_max),
    y_min: coordinate(raw.y_min), y_max: coordinate(raw.y_max), axes: bool(raw.axes ?? true),
    lines: array(raw.lines ?? [], 0, 32).map((value) => {
      const line = object(value);
      keys(line, ['points', 'dashed']);
      return { points: array(line.points, 2, 201).map(point), dashed: bool(line.dashed ?? false) };
    }),
    circles: array(raw.circles ?? [], 0, 16).map((value) => {
      const circle = object(value);
      keys(circle, ['center', 'radius']);
      const radius = coordinate(circle.radius);
      if (radius <= 0) invalid();
      return { center: point(circle.center), radius };
    }),
    labels: array(raw.labels ?? [], 0, 48).map((value) => {
      const label = object(value);
      keys(label, ['x', 'y', 'text']);
      return { x: coordinate(label.x), y: coordinate(label.y), text: text(label.text, 1, 100) };
    }),
  };
  if (parsed.x_min >= parsed.x_max || parsed.y_min >= parsed.y_max) invalid();
  return parsed;
}

function rounding(value: unknown): PublicTask['rounding'] {
  if (value === null || value === undefined) return null;
  const raw = object(value);
  keys(raw, ['digits', 'mode', 'instruction']);
  return { digits: integer(raw.digits, 0, 10), mode: choice(raw.mode, ['half_up', 'floor', 'ceil']), instruction: text(raw.instruction, 1, 300) };
}

function table(value: unknown): PublicTask['table'] {
  if (value === null) return null;
  const raw = object(value);
  keys(raw, ['headers', 'rows']);
  const headers = strings(raw.headers, 1);
  const rows = array(raw.rows, 1).map((row) => strings(row));
  if (rows.some((row) => row.length !== headers.length)) invalid();
  return { headers, rows };
}

export function taskData(value: unknown, instanceKey: string): OfflineTask {
  safeData(value);
  const raw = object(value);
  keys(raw, ['id', 'revision', 'slot', 'slot_id', 'topic', 'title', 'statement', 'formula', 'table', 'skill_ids',
    'family_id', 'estimated_seconds', 'review_status', 'hint_count', 'figure', 'rounding', 'answer', 'hints', 'solution',
    'source', 'profile_id', 'difficulty', 'generation']);
  const source = object(raw.source);
  keys(source, ['author', 'origin', 'rights', 'reviewed_by']);
  const generation = raw.generation == null ? null : object(raw.generation);
  if (generation) keys(generation, ['template_id', 'template_version', 'seed']);
  const parsed: OfflineTask = {
    id: identifier(raw.id), revision: identifier(raw.revision), slot: integer(raw.slot, 1),
    slot_id: raw.slot_id == null ? null : identifier(raw.slot_id), topic: text(raw.topic), title: text(raw.title),
    statement: text(raw.statement, 1), formula: raw.formula === null ? null : text(raw.formula), table: table(raw.table),
    skill_ids: strings(raw.skill_ids, 1, true), family_id: identifier(raw.family_id),
    estimated_seconds: integer(raw.estimated_seconds, 1, 86_400), review_status: choice(raw.review_status, ['demo', 'reviewed']),
    hint_count: integer(raw.hint_count, 0, 3), figure: figure(raw.figure), rounding: rounding(raw.rounding),
    answer: text(raw.answer, 1, 64), hints: strings(raw.hints, 3), solution: strings(raw.solution, 1),
    source: { author: text(source.author), origin: text(source.origin), rights: text(source.rights),
      reviewed_by: source.reviewed_by === null ? null : identifier(source.reviewed_by) },
    profile_id: identifier(raw.profile_id), difficulty: choice(raw.difficulty, [1, 2, 3]),
    generation: generation ? { template_id: identifier(generation.template_id), template_version: identifier(generation.template_version), seed: integer(generation.seed, 0, 2 ** 32 - 1) } : null,
    instance_key: instanceKey,
  };
  if (!HASH.test(instanceKey) || parsed.hints.length !== 3 || parsed.hint_count !== parsed.hints.length
    || [...parsed.hints, ...parsed.solution].some((item) => !item.trim()) || !parsed.statement.trim()) invalid();
  unique(parsed.skill_ids);
  const reference = parseAnswer(parsed.answer, 'exam');
  if (parsed.rounding && (!parsed.statement.includes(parsed.rounding.instruction)
    || (reference.value.numerator * 10n ** BigInt(parsed.rounding.digits)) % reference.value.denominator !== 0n)) invalid();
  if (parsed.review_status === 'reviewed' && (!parsed.source.reviewed_by || parsed.source.reviewed_by === parsed.source.author)) invalid();
  return parsed;
}

function example(value: unknown) {
  const raw = object(value);
  keys(raw, ['statement', 'steps', 'answer']);
  return { statement: text(raw.statement), steps: strings(raw.steps, 1), answer: text(raw.answer) };
}

export function lessonData(value: unknown): Lesson & { reviewed_by: string | null } {
  safeData(value);
  const raw = object(value);
  keys(raw, ['id', 'title', 'slot', 'minutes', 'skill_ids', 'sections', 'example', 'takeaway', 'revision', 'slot_id',
    'family_ids', 'practice_task_ids', 'prerequisite_ids', 'examples', 'review_status', 'author_id', 'reviewed_by', 'kind', 'related_slot_ids']);
  const parsed = {
    id: identifier(raw.id), title: text(raw.title), slot: integer(raw.slot), minutes: integer(raw.minutes, 1),
    skill_ids: strings(raw.skill_ids, 1, true), sections: array(raw.sections, 1).map((value) => {
      const section = object(value);
      keys(section, ['heading', 'body', 'formula']);
      return { heading: text(section.heading), body: text(section.body), formula: section.formula === null ? null : text(section.formula) };
    }), example: example(raw.example), takeaway: text(raw.takeaway), revision: identifier(raw.revision ?? '1'),
    slot_id: raw.slot_id == null ? null : identifier(raw.slot_id), family_ids: strings(raw.family_ids ?? [], 0, true),
    practice_task_ids: strings(raw.practice_task_ids ?? [], 0, true), prerequisite_ids: strings(raw.prerequisite_ids ?? [], 0, true),
    examples: array(raw.examples ?? []).map(example), review_status: choice(raw.review_status ?? 'demo', ['demo', 'reviewed']),
    author_id: raw.author_id == null ? null : identifier(raw.author_id), reviewed_by: raw.reviewed_by == null ? null : identifier(raw.reviewed_by),
    kind: choice(raw.kind ?? 'exam', ['exam', 'foundation']), related_slot_ids: strings(raw.related_slot_ids ?? [], 0, true),
  };
  if (parsed.review_status === 'reviewed' && (!parsed.author_id || !parsed.reviewed_by || parsed.author_id === parsed.reviewed_by)) invalid();
  return parsed;
}

export function profileData(value: unknown, tasks: OfflineTask[]): Profile {
  safeData(value);
  const raw = object(value);
  keys(raw, ['id', 'year', 'title', 'status', 'revision', 'verified_at', 'verification_note', 'source_urls', 'slots']);
  const parsed: Profile = {
    id: identifier(raw.id), year: integer(raw.year), title: text(raw.title), status: choice(raw.status, ['draft', 'approved']),
    revision: identifier(raw.revision), verified_at: text(raw.verified_at), verification_note: text(raw.verification_note),
    source_urls: strings(raw.source_urls), demo_mode: tasks.some((task) => task.review_status === 'demo'), bank_size: tasks.length,
    slots: array(raw.slots, 1).map((value) => {
      const slot = object(value);
      keys(slot, ['number', 'id', 'title', 'level', 'summary', 'skills', 'lesson_id']);
      const number = integer(slot.number, 1);
      const skills = array(slot.skills, 1).map((value) => {
        const skill = object(value);
        keys(skill, ['id', 'title']);
        return { id: identifier(skill.id), title: text(skill.title) };
      });
      unique(skills.map((skill) => skill.id));
      return { number, id: identifier(slot.id), title: text(slot.title), level: choice(slot.level, ['Б', 'П']), summary: text(slot.summary),
        skills, lesson_id: identifier(slot.lesson_id), available_tasks: tasks.filter((task) => task.slot === number).length };
    }),
  };
  unique(parsed.slots.map((slot) => slot.number));
  unique(parsed.slots.map((slot) => slot.id));
  for (const source of parsed.source_urls) {
    let url: URL;
    try { url = new URL(source); } catch { invalid(); }
    if (!['http:', 'https:'].includes(url.protocol) || !url.hostname) invalid();
  }
  return parsed;
}

export function validateLinks(profile: Profile, lessons: Lesson[], tasks: OfflineTask[]): void {
  unique(tasks.map((task) => task.id));
  unique(lessons.map((lesson) => lesson.id));
  const slots = new Map(profile.slots.map((slot) => [slot.number, slot]));
  const slotIds = new Set(profile.slots.map((slot) => slot.id));
  const lessonById = new Map(lessons.map((lesson) => [lesson.id, lesson]));
  const taskById = new Map(tasks.map((task) => [task.id, task]));
  const families = new Set(tasks.map((task) => task.family_id));
  for (const slot of profile.slots) {
    const lesson = lessonById.get(slot.lesson_id);
    if (!lesson || lesson.slot !== slot.number || lesson.kind !== 'exam') invalid();
  }
  for (const item of [...tasks, ...lessons]) {
    if ('kind' in item && item.kind === 'foundation') {
      if (item.slot !== 0 || item.slot_id !== null || !item.related_slot_ids?.length
        || item.related_slot_ids.some((id) => !slotIds.has(id))) invalid();
      continue;
    }
    const slot = slots.get(item.slot);
    if (!slot || item.skill_ids.some((id) => !slot.skills.some((skill) => skill.id === id))
      || (item.slot_id != null && item.slot_id !== slot.id)) invalid();
  }
  for (const task of tasks) if (task.profile_id !== profile.id) invalid();
  for (const lesson of lessons) {
    if (lesson.family_ids?.some((id) => !families.has(id))) invalid();
    for (const id of lesson.practice_task_ids ?? []) {
      const task = taskById.get(id);
      if (!task || task.slot !== lesson.slot || (lesson.family_ids?.length && !lesson.family_ids.includes(task.family_id))) invalid();
    }
  }
  const visiting = new Set<string>();
  const visited = new Set<string>();
  function visit(id: string): void {
    if (visiting.has(id)) invalid('Цикл предварительных уроков.');
    if (visited.has(id)) return;
    const lesson = lessonById.get(id);
    if (!lesson) invalid();
    visiting.add(id);
    for (const prerequisite of lesson.prerequisite_ids ?? []) visit(prerequisite);
    visiting.delete(id);
    visited.add(id);
  }
  for (const lesson of lessons) visit(lesson.id);
}
