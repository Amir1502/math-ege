import type { PublicTask } from '../api/types';

export type AssessmentMode = 'diagnostic' | 'exam';
export type AssessmentStatus = 'prepared' | 'active' | 'awaiting_snapshot' | 'completed';
export type Answer = { answer: string; active_seconds: number };
export type AnswerMap = Record<string, Answer>;
export type WriterBody = { device_id: string; writer_generation: number };
export type PrepareBody = { mode: AssessmentMode; duration_minutes: number; device_id: string };
export type DraftBody = WriterBody & { expected_revision: number; current_index: number; answers: AnswerMap };
export type FinishBody = WriterBody & { answers: AnswerMap; connection_lost: boolean };
export type Pending<T> = { key: string; body: T };

export type ResultRow = {
  task_id: string;
  raw_answer: string;
  normalized_answer: string | null;
  expected_answer: string;
  correct: boolean;
  skipped: boolean;
  format_error: boolean;
  format_message: string | null;
  independent: boolean;
  assisted: boolean;
  solution: string[];
};

export type AssessmentResult = {
  score: number;
  total: 13;
  rows: ResultRow[];
  connection_lost: boolean;
  recommendation: string;
};

export type AssessmentView = {
  id: string;
  mode: AssessmentMode;
  status: AssessmentStatus;
  server_now: string;
  started_at: string | null;
  deadline_at: string | null;
  duration_minutes: number;
  writer_generation: number;
  can_write: boolean;
  draft_revision: number;
  current_index: number;
  tasks: PublicTask[];
  drafts: AnswerMap;
  server_result: AssessmentResult | null;
  local_result: AssessmentResult | null;
  result_notice: string;
};

export interface AssessmentApi {
  guest(): Promise<{ id: string }>;
  prepare(body: PrepareBody, key: string): Promise<AssessmentView>;
  get(id: string, deviceId: string): Promise<AssessmentView>;
  activate(id: string, body: WriterBody, key: string): Promise<AssessmentView>;
  draft(id: string, body: DraftBody): Promise<{ draft_revision: number }>;
  takeover(id: string, body: WriterBody, key: string): Promise<AssessmentView>;
  finish(id: string, body: FinishBody, key: string): Promise<AssessmentView>;
}
