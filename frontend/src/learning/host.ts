import type { LearningApi } from '../api/client';
import type { SessionRecord, SessionSnapshot } from './model';
import type { SerialQueue } from './serial';

export interface SessionHost {
  readonly id: string;
  readonly api: LearningApi;
  readonly queue: SerialQueue;
  getSnapshot(): SessionSnapshot;
  update(change: (record: SessionRecord) => SessionRecord): Promise<void>;
  patch(change: Partial<SessionSnapshot>): void;
}
