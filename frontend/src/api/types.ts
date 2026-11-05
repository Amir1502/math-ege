export type Skill = { id: string; title: string };

export type Slot = {
  number: number;
  id: string;
  title: string;
  level: 'Б' | 'П';
  summary: string;
  skills: Skill[];
  available_tasks: number;
  lesson_id: string;
};

export type Profile = {
  id: string;
  year: number;
  title: string;
  status: 'draft' | 'approved';
  revision: string;
  verified_at: string;
  verification_note: string;
  source_urls: string[];
  demo_mode: boolean;
  bank_size: number;
  slots: Slot[];
};

/** Frozen source revision, without the current bank's runtime availability. */
export type SlotSource = Omit<Slot, 'available_tasks'>;
export type ProfileSource = Omit<Profile, 'demo_mode' | 'bank_size' | 'slots'> & { slots: SlotSource[] };

export type Lesson = {
  id: string;
  title: string;
  slot: number;
  minutes: number;
  skill_ids: string[];
  sections: { heading: string; body: string; formula: string | null }[];
  example: { statement: string; steps: string[]; answer: string };
  takeaway: string;
  revision?: string;
  slot_id?: string | null;
  family_ids?: string[];
  practice_task_ids?: string[];
  prerequisite_ids?: string[];
  examples?: { statement: string; steps: string[]; answer: string }[];
  review_status?: 'demo' | 'reviewed';
  kind?: 'exam' | 'foundation';
  related_slot_ids?: string[];
};

export type Figure = {
  description: string;
  x_min: number; x_max: number; y_min: number; y_max: number;
  axes: boolean;
  lines: { points: { x: number; y: number }[]; dashed?: boolean }[];
  circles: { center: { x: number; y: number }; radius: number }[];
  labels: { x: number; y: number; text: string }[];
};

export type PublicTask = {
  id: string;
  revision: string;
  slot: number;
  topic: string;
  title: string;
  statement: string;
  formula: string | null;
  table: { headers: string[]; rows: string[][] } | null;
  skill_ids: string[];
  family_id: string;
  estimated_seconds: number;
  review_status: 'demo' | 'reviewed';
  hint_count: number;
  slot_id?: string | null;
  figure?: Figure | null;
  rounding?: { digits: number; mode: 'half_up' | 'floor' | 'ceil'; instruction: string } | null;
};

export type Attempt = {
  id: string;
  task_id: string;
  raw_answer: string;
  normalized_answer: string | null;
  correct: boolean;
  assisted: boolean;
  first_attempt: boolean;
  independent: boolean;
  skipped: boolean;
  active_seconds: number;
  created_at: string;
  expected_answer: string;
  solution: string[];
};

export type Summary = {
  total: number;
  answered: number;
  independent_total: number;
  independent_correct: number;
  assisted: number;
  corrections: number;
  skipped: number;
  active_seconds: number;
};

export type Hint = { level: number; text: string };
export type Solution = { answer: string; steps: string[] };

export type LearningSession = {
  id: string;
  profile_id: string;
  profile_revision?: string | null;
  profile?: ProfileSource | null;
  mode: 'practice';
  status: 'active' | 'completed';
  created_at: string;
  completed_at: string | null;
  current_index: number;
  requested_length: number;
  notice: string | null;
  draft_revision: number;
  tasks: PublicTask[];
  attempts: Attempt[];
  drafts: Record<string, { answer: string; active_seconds: number }>;
  help: Record<string, { hints: Hint[]; solution: Solution | null }>;
  summary: Summary;
  options?: StartBody | null;
};

export type Progress = {
  independent_total: number;
  independent_correct: number;
  assisted_total: number;
  corrections_total: number;
  skipped_total: number;
  active_session_id: string | null;
  slots: {
    number: number;
    attempts: number;
    correct: number;
    status: 'Нет данных' | 'Изучаю' | 'Закрепляю' | 'Освоено';
    covered_skills: number;
    total_skills: number;
  }[];
  recent_sessions: { id: string; status: 'active' | 'completed'; created_at: string; summary: Summary }[];
  mistakes: { task: PublicTask; attempt: Attempt }[];
};

export type ExportFigure = Omit<Figure, 'lines'> & {
  lines: { points: { x: number; y: number }[]; dashed: boolean }[];
};

export type ExportPublicTask = Omit<PublicTask, 'slot_id' | 'figure' | 'rounding'> & {
  slot_id: string | null;
  figure: ExportFigure | null;
  rounding: Exclude<PublicTask['rounding'], undefined>;
};

export type ExportSessionOptions = Required<StartBody>;

/** Historical fields are mandatory in a complete export, optional in older session responses. */
export type ExportLearningSession = Omit<LearningSession, 'profile_revision' | 'profile' | 'tasks' | 'options'> & {
  profile_revision: string;
  profile: ProfileSource;
  tasks: ExportPublicTask[];
  options: ExportSessionOptions | null;
};

export type ExportDraftAnswer = { answer: string; active_seconds: number };
export type ExportFirstDraft = ExportDraftAnswer & { recorded_at: string };

/** Preserve the released backend wire names, not the assessment UI's adapted fields. */
export type ExportAssessmentRow = {
  id: string;
  task_id: string;
  task_revision: string;
  slot: number;
  slot_id: string;
  family_id: string;
  skill_ids: string[];
  raw: string;
  normalized: string | null;
  expected: string;
  correct: boolean;
  skipped: boolean;
  format_error: boolean;
  format_message: string | null;
  independent: boolean;
  assisted: boolean;
  first_attempt: boolean;
  active_seconds: number;
  solution: string[];
  first_draft: ExportFirstDraft | null;
  first_answer: ExportFirstDraft | null;
  label: 'Верно' | 'Неверно' | 'Пропущено' | 'Ошибка формата';
};

export type ExportAssessmentResult = {
  source: 'server' | 'local';
  reason: 'finished' | 'deadline' | 'connection_lost';
  label: string;
  score: number;
  total: 13;
  answered: number;
  skipped: number;
  format_errors: number;
  independent_total: number;
  independent_correct: number;
  assisted_total: number;
  active_seconds: number;
  elapsed_seconds: number;
  snapshot_at: string;
  snapshot_hash: string;
  connection_lost: boolean;
  checker_revision: string;
  rows: ExportAssessmentRow[];
  weak_skill_ids: string[];
  recommendation: string;
};

export type ExportAssessment = {
  id: string;
  mode: 'diagnostic' | 'exam';
  status: 'prepared' | 'active' | 'awaiting_snapshot' | 'completed';
  profile_id: string;
  profile_revision: string;
  profile: ProfileSource;
  created_at: string;
  started_at: string | null;
  deadline_at: string | null;
  released_at: string | null;
  duration_minutes: number;
  tasks: ExportPublicTask[];
  drafts: Record<string, ExportDraftAnswer>;
  server_result: ExportAssessmentResult | null;
  local_result: ExportAssessmentResult | null;
  result_notice: string;
};

export type ExportAnnotation = {
  id: string;
  session_id: string;
  task_id: string;
  favourite: boolean;
  manual: boolean;
  not_understood: boolean;
  cause: 'theory' | 'model' | 'calculation' | 'restriction' | 'graph' | 'format' | null;
  created_at: string;
  updated_at: string;
};

export type ExportReview = {
  skill_id: string;
  family_id: string;
  slot_id: string;
  due_at: string | null;
  interval_days: number;
  closed: boolean;
  anchor_task_id: string;
  anchor_at: string;
};

export type ExportCorrection = {
  task_id: string;
  task_revision: string;
  reason: string;
  created_at: string;
  attempt_ids: string[];
  session_ids: string[];
  assessment_ids: string[];
};

export type ExportLearning = {
  algorithm_version: string;
  annotations: ExportAnnotation[];
  reviews: ExportReview[];
  corrections: ExportCorrection[];
};

/** Minimal account data; authentication state and owner credentials are not exported. */
export type ExportAccount = {
  id: string;
  email: string;
  created_at: string;
  email_verified_at: string;
  role: 'student' | 'methodist' | 'admin';
  daily_minutes: 10 | 20 | 30;
  consents: { policy_version: string; accepted_at: string }[];
  deletion_request: {
    id: string;
    status: 'requested';
    requested_at: string;
    deadline_at: string;
  } | null;
};

export type HistoryExport = {
  version: '1';
  exported_at: string;
  profile_id: string;
  sessions: ExportLearningSession[];
  assessments: ExportAssessment[];
  learning: ExportLearning;
  account: ExportAccount | null;
};

export type StartBody = {
  slots: number[]; length: 5 | 10 | 20; mode: 'practice';
  skill_ids?: string[]; family_ids?: string[]; difficulty?: 1 | 2 | 3 | null;
  selection?: 'balanced' | 'mixed'; repeat_task_id?: string | null;
  until_stopped?: boolean; target_minutes?: 10 | 20 | 30 | null;
};
export type AttemptBody = { task_id: string; answer: string; active_seconds: number; skipped: boolean };
export type DraftBody = { task_id: string; answer: string; active_seconds: number; expected_revision: number };
