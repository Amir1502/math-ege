import type { AttemptBody, LearningSession, StartBody } from '../api/types';
import type { ApiError } from '../api/client';

export type LocalDraft = {
  answer: string;
  active_seconds: number;
  version: number;
  synced_version: number;
};

export type PendingAttempt = { key: string; body: AttemptBody };
export type PendingStart = { key: string; body: StartBody };

export type SessionRecord = {
  session: LearningSession;
  drafts: Record<string, LocalDraft>;
  current_index: number;
  pending_attempt: PendingAttempt | null;
  finish_key: string | null;
  pending_finish: boolean;
  extension_key?: string | null;
  extension_start?: number;
  saved_at: number;
};

export type SessionSnapshot = {
  record: SessionRecord | null;
  loading: boolean;
  busy: 'attempt' | 'help' | 'finish' | 'extend' | null;
  syncing: boolean;
  conflict: boolean;
  error: string | null;
  formError: ApiError | null;
  storageError: string | null;
  accessDenied: boolean;
};

export function createRecord(session: LearningSession): SessionRecord {
  const drafts: Record<string, LocalDraft> = {};
  for (const task of session.tasks) {
    const draft = session.drafts[task.id];
    const attempts = session.attempts.filter((item) => item.task_id === task.id);
    drafts[task.id] = {
      answer: draft?.answer ?? attempts.at(-1)?.raw_answer ?? '',
      active_seconds: Math.max(draft?.active_seconds ?? 0, ...attempts.map((item) => item.active_seconds)),
      version: 0,
      synced_version: 0,
    };
  }
  return {
    session,
    drafts,
    current_index: session.current_index,
    pending_attempt: null,
    finish_key: null,
    pending_finish: false,
    saved_at: Date.now(),
  };
}

export function hasDirtyDrafts(record: SessionRecord) {
  return Object.values(record.drafts).some((draft) => draft.version > draft.synced_version);
}
