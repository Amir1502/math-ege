import type { Attempt, PublicTask, Summary } from '../api/types';

export type PlanMinutes = 10 | 20 | 30;
export type PlanLength = 5 | 10 | 20;
export type MasteryStatus = 'Нет данных' | 'Изучаю' | 'Закрепляю' | 'Освоено';
export type ErrorCause = 'theory' | 'model' | 'calculation' | 'restriction' | 'graph' | 'format';

export type SkillEvidence = { id: string; title: string; attempts: number; correct: number };
export type SlotEvidence = {
  slot_id: string;
  number: number;
  title: string;
  status: MasteryStatus;
  attempts: number;
  correct: number;
  covered_skills: number;
  total_skills: number;
  skills: SkillEvidence[];
};

export type ScheduledReview = {
  skill_id: string;
  family_id: string;
  slot_id: string;
  slot: number | null;
  due_at: string;
  interval_days: number;
  overdue: boolean;
};
export type WeakSkill = { id: string; title: string; slot: number; family_ids: string[] };
export type Favourite = { task: PublicTask; session_id: string; profile: OriginalProfile | null };
export type JournalEntry = Favourite & {
  id: string;
  attempt: Attempt | null;
  cause: ErrorCause | null;
  manual: boolean;
  not_understood: boolean;
};

export type OriginalProfile = {
  id: string;
  title: string | null;
  year: number | null;
  revision: string | null;
};
export type AssessmentHistory = {
  id: string;
  mode: 'diagnostic' | 'exam';
  released_at: string;
  snapshot_at: string;
  score: number;
  total: 13;
  answered: number;
  skipped: number;
  format_errors: number;
  active_seconds: number;
  elapsed_seconds: number;
  profile: OriginalProfile;
};
export type DashboardCollection = 'reviews' | 'weak_skills' | 'favourites' | 'journal' | 'assessment_history' | 'notifications';
export type LearningDashboard = {
  algorithm_version: string;
  notice: string | null;
  independent_total: number;
  independent_correct: number;
  assisted_total: number;
  corrections_total: number;
  skipped_total: number;
  excluded_total: number;
  slots: SlotEvidence[];
  reviews: ScheduledReview[];
  weak_skills: WeakSkill[];
  favourites: Favourite[];
  journal: JournalEntry[];
  assessment_history: AssessmentHistory[];
  notifications: { id: string; message: string; created_at: string }[];
  recommendation: string;
  pagination: { offset: number; limit: number; totals: Partial<Record<DashboardCollection, number>> };
};

export type TimePlan = {
  minutes: PlanMinutes;
  length: PlanLength;
  estimated_seconds: number;
  slots: number[];
  selection: 'mixed';
  notice: string | null;
};

export type PracticeHistory = {
  id: string;
  status: 'active' | 'completed';
  created_at: string;
  summary: Summary;
  profile: OriginalProfile | null;
};

/** Canonical learning counters with practice history; excludes /progress.mistakes and full sessions. */
export type PracticeProgress = {
  algorithm_version: string;
  notice: string | null;
  excluded_total: number;
  independent_total: number;
  independent_correct: number;
  assisted_total: number;
  corrections_total: number;
  skipped_total: number;
  active_session_id: string | null;
  active_assessment_id: string | null;
  slots: Omit<SlotEvidence, 'slot_id' | 'title' | 'skills'>[];
  recent_sessions: PracticeHistory[];
};

export type AnnotationPatch = {
  favourite?: boolean;
  manual?: boolean;
  not_understood?: boolean;
  cause?: ErrorCause | null;
};
export type AnnotationBody = AnnotationPatch & { session_id: string; task_id: string };
export type AnnotationValues = Required<AnnotationPatch>;
export type SavedAnnotation = AnnotationValues & { session_id: string; task_id: string };

export interface LearningExtrasApi {
  dashboard(page?: { offset: number; limit?: number }): Promise<LearningDashboard>;
  plan(minutes: PlanMinutes): Promise<TimePlan>;
  progress(): Promise<PracticeProgress>;
  annotations(isCurrent?: () => boolean): Promise<SavedAnnotation[]>;
  annotate(body: AnnotationBody, key: string): Promise<SavedAnnotation>;
}

export interface IdentityReader { current(): string | null }

export type ResourceSnapshot<T> = {
  owner: string | null;
  data: T | null;
  loading: boolean;
  ready: boolean;
  error: string | null;
};
