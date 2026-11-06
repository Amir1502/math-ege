import type { Lesson, Profile, PublicTask } from '../api/types';

export type {
  Attempt, AttemptBody, DraftBody, Hint, LearningSession, Lesson, Profile,
  ProfileSource, Progress, PublicTask, Solution, StartBody, Summary,
} from '../api/types';

export type OfflineTask = PublicTask & {
  answer: string;
  hints: string[];
  solution: string[];
  source: { author: string; origin: string; rights: string; reviewed_by: string | null };
  profile_id: string;
  difficulty: 1 | 2 | 3;
  generation?: { template_id: string; template_version: string; seed: number } | null;
  instance_key: string;
};

export type OfflineCourse = {
  version: '1';
  package_revision: string;
  profile: Profile;
  lessons: Lesson[];
  tasks: OfflineTask[];
};

/** Local domain and storage errors use the same machine-readable boundary. */
export class OfflineError extends Error {
  readonly code: string;
  readonly field: string | null;

  constructor(code: string, message: string, field: string | null = null) {
    super(message);
    this.name = 'OfflineError';
    this.code = code;
    this.field = field;
  }
}
