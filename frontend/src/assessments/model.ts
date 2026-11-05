import type { AnswerMap, AssessmentView, FinishBody, Pending, WriterBody } from './types';

export type ClockAnchor = { server_ms: number; wall_ms: number; floor_ms: number };
export type AssessmentConflict = 'revision' | 'writer' | 'access' | null;

export type AssessmentRecord = {
  schema: 1;
  owner_id: string;
  device_id: string;
  view: AssessmentView;
  drafts: AnswerMap;
  current_index: number;
  local_version: number;
  acknowledged_version: number;
  sequence: number;
  clock: ClockAnchor;
  conflict: AssessmentConflict;
  connection_lost: boolean;
  pending_activation: Pending<WriterBody> | null;
  pending_takeover: Pending<WriterBody> | null;
  frozen: Pending<FinishBody> | null;
};

export interface AssessmentStorage {
  load(ownerId: string, id: string, deviceId: string): Promise<AssessmentRecord | undefined>;
  save(record: AssessmentRecord): Promise<void>;
  journal(record: AssessmentRecord): void;
}

export type AssessmentSnapshot = {
  record: AssessmentRecord | null;
  loading: boolean;
  busy: 'activate' | 'takeover' | 'finish' | null;
  syncing: boolean;
  online: boolean;
  error: string | null;
  storageError: string | null;
  dirty: boolean;
  readOnly: boolean;
  remainingSeconds: number | null;
};

export function answersFor(view: AssessmentView): AnswerMap {
  return Object.fromEntries(view.tasks.map((task) => [task.id, {
    answer: view.drafts[task.id]?.answer ?? '',
    active_seconds: view.drafts[task.id]?.active_seconds ?? 0,
  }]));
}

export function createAssessmentRecord(view: AssessmentView, ownerId: string, deviceId: string): AssessmentRecord {
  return {
    schema: 1, owner_id: ownerId, device_id: deviceId, view,
    drafts: answersFor(view), current_index: view.current_index, local_version: 0,
    acknowledged_version: 0, sequence: 0, conflict: view.can_write ? null : 'writer',
    clock: { server_ms: Date.parse(view.server_now), floor_ms: Date.parse(view.server_now), wall_ms: Date.now() },
    connection_lost: false, pending_activation: null, pending_takeover: null, frozen: null,
  };
}

export function hasLocalChanges(record: AssessmentRecord): boolean {
  return record.local_version > record.acknowledged_version;
}

export function canEdit(record: AssessmentRecord | null): boolean {
  return Boolean(record && record.view.status === 'active' && record.view.can_write && !record.conflict && !record.frozen);
}

export function canFreeze(record: AssessmentRecord | null): boolean {
  return Boolean(record && ['active', 'awaiting_snapshot'].includes(record.view.status)
    && record.view.can_write && record.conflict !== 'writer' && record.conflict !== 'access' && !record.frozen);
}

export function assessmentPhase(record: AssessmentRecord): AssessmentView['status'] {
  return record.frozen && record.view.status !== 'completed' ? 'awaiting_snapshot' : record.view.status;
}
