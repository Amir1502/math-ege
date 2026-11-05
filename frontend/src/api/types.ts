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
  status: 'draft';
  revision: string;
  verified_at: string;
  verification_note: string;
  source_urls: string[];
  demo_mode: boolean;
  bank_size: number;
  slots: Slot[];
};

export type Lesson = {
  id: string;
  title: string;
  slot: number;
  minutes: number;
  skill_ids: string[];
  sections: { heading: string; body: string; formula: string | null }[];
  example: { statement: string; steps: string[]; answer: string };
  takeaway: string;
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
  review_status: 'demo';
  hint_count: number;
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
    status: 'Нет данных' | 'Изучаю' | 'Закрепляю';
    covered_skills: number;
    total_skills: number;
  }[];
  recent_sessions: { id: string; status: 'active' | 'completed'; created_at: string; summary: Summary }[];
  mistakes: { task: PublicTask; attempt: Attempt }[];
};

export type HistoryExport = {
  version: '1';
  exported_at: string;
  profile_id: string;
  sessions: LearningSession[];
};

export type StartBody = { slots: number[]; length: 5 | 10 | 20; mode: 'practice' };
export type AttemptBody = { task_id: string; answer: string; active_seconds: number; skipped: boolean };
export type DraftBody = { task_id: string; answer: string; active_seconds: number; expected_revision: number };
