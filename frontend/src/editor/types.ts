/** Private editor DTOs. Student history and its cache are not editor transports. */
export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
export type JsonObject = { [key: string]: JsonValue };
export type Kind = 'task' | 'lesson' | 'profile' | 'template';
export type Status = 'draft' | 'review' | 'ready' | 'published' | 'archived';
export type Capability = 'edit' | 'submit' | 'return_to_draft' | 'approve' | 'publish' | 'fork'
  | 'archive' | 'withdraw' | 'run_checks' | 'review_sample';

export type EditorSlot = {
  id: string; number: number; title: string; level: 'Б' | 'П'; summary: string;
  skills: { id: string; title: string }[]; lesson_id: string;
};
export type EditorProfile = {
  id: string; title: string; year: number; status: 'draft' | 'approved';
  revision?: string; verified_at: string; verification_note: string;
  source_urls: string[]; slots: EditorSlot[];
};
export type EditorMeta = {
  actor: { id: string; role: 'methodist' | 'admin'; owner_id: string };
  profile: EditorProfile; kinds: Kind[]; statuses: Status[];
  max_import_items: number; max_request_bytes: number;
  templates: { id: string; title: string; slot: number; skill_ids: string[] }[];
};
export type RevisionSummary = {
  id: string; kind: Kind; content_id: string; content_revision: string; title: string;
  version: number; revision: number; status: Status; author_id: string; reviewer_id: string | null;
  change_note: string; created_at: string; updated_at: string; capabilities: Capability[];
};
export type AuditEvent = {
  id: string; actor_id: string; actor_role: string; action: string;
  from_status: string | null; to_status: string | null; note: string; created_at: string;
};
export type Evidence = {
  automated_seeds: number; automated_passed: boolean; reviewed_seeds: number[];
  rejected_seeds: number[]; checks: string[]; failure: string | null;
};
export type Revision = RevisionSummary & {
  payload: JsonObject; review_note: string | null; published_at: string | null;
  audit: AuditEvent[]; evidence: Evidence | null;
};
export type RevisionList = { items: RevisionSummary[]; total: number; limit: number; offset: number };
export type BaseItem = { kind: Kind; content_id: string; title: string; content_revision: string };
export type BaseList = { items: BaseItem[]; total: number };
export type PublicationRef = { id: string; expected_revision: number };

export type EditorFigure = {
  description: string; x_min: number; x_max: number; y_min: number; y_max: number; axes: boolean;
  lines: { points: { x: number; y: number }[]; dashed: boolean }[];
  circles: { center: { x: number; y: number }; radius: number }[];
  labels: { x: number; y: number; text: string }[];
};
/** Structurally compatible with the safe shared TaskContent renderer. */
export type PreviewTask = {
  id: string; revision: string; slot: number; slot_id: string | null; topic: string;
  title: string; statement: string; formula: string | null;
  table: { headers: string[]; rows: string[][] } | null;
  skill_ids: string[]; family_id: string; estimated_seconds: number;
  review_status: 'demo' | 'reviewed'; hint_count: number; figure: EditorFigure | null;
  rounding: { digits: number; mode: 'half_up' | 'floor' | 'ceil'; instruction: string } | null;
};
export type WorkedExample = { statement: string; steps: string[]; answer: string };
export type PreviewLesson = {
  title: string; sections: { heading: string; body: string; formula: string | null }[];
  example: WorkedExample; examples: WorkedExample[]; takeaway: string;
};
export type Preview = { kind: Kind; task: PreviewTask | null; payload: JsonObject; message: string };
export type TemplateSample = {
  seed: number; output_hash: string; task: PreviewTask; answer: string; solution: string[]; hints: string[];
};
export type CheckResult = { id: string; passed: boolean; seed_count: number; checks: string[]; failure: string | null };
export type Withdrawal = {
  task_id: string; task_revision: string; reason: string; created_at: string; historical_scores_unchanged: true;
};

export const kindLabels: Record<Kind, string> = {
  task: 'Задачи', lesson: 'Уроки', profile: 'Профили', template: 'Шаблоны',
};
export const statusLabels: Record<Status, string> = {
  draft: 'Черновик', review: 'Предметная проверка', ready: 'Готово к публикации',
  published: 'Опубликовано', archived: 'Архив',
};
export const actionLabels: Record<Capability, string> = {
  edit: 'Сохранить черновик', submit: 'На предметную проверку', return_to_draft: 'Вернуть в черновик',
  approve: 'Подтвердить проверку', publish: 'Опубликовать', fork: 'Создать новую редакцию',
  archive: 'В архив', withdraw: 'Снять с выдачи', run_checks: 'Проверить 1000 seed',
  review_sample: 'Сохранить рецензию',
};
