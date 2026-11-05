import { ApiError, errorText } from '../api/client';
import type { SessionHost } from './host';
import { mergeSession } from './merge';
import { hasDirtyDrafts } from './model';

/** One revision stream per session. A response acknowledges only the version it actually sent. */
export class DraftSync {
  private timer: ReturnType<typeof setTimeout> | undefined;
  private running: Promise<void> | null = null;
  private retryAfter = 0;

  constructor(private readonly host: SessionHost) {}

  schedule() {
    if (this.timer || this.running || this.host.getSnapshot().conflict) return;
    const delay = Math.max(700, this.retryAfter - Date.now());
    this.timer = setTimeout(() => {
      this.timer = undefined;
      void this.flush();
    }, delay);
  }

  flush(): Promise<void> {
    if (this.timer) clearTimeout(this.timer);
    this.timer = undefined;
    if (this.running) return this.running;
    this.running = this.host.queue.run(async () => {
      const initial = this.host.getSnapshot();
      if (!initial.record || initial.record.session.status !== 'active' || initial.accessDenied || initial.conflict) return;
      if (!hasDirtyDrafts(initial.record)) return;
      this.host.patch({ syncing: true });
      try {
        // A bounded pass avoids starving an answer or finish queued during continuous typing.
        const ids = Object.keys(initial.record.drafts);
        const currentId = initial.record.session.tasks[initial.record.current_index]?.id;
        ids.sort((a, b) => Number(a === currentId) - Number(b === currentId));
        for (const taskId of ids) {
          const record = this.host.getSnapshot().record;
          const draft = record?.drafts[taskId];
          if (!record || !draft || draft.version <= draft.synced_version) continue;
          const sent = { ...draft };
          const response = await this.host.api.draft(this.host.id, {
            task_id: taskId,
            answer: sent.answer,
            active_seconds: sent.active_seconds,
            expected_revision: record.session.draft_revision,
          });
          await this.host.update((latest) => ({
            ...latest,
            session: { ...latest.session, draft_revision: response.draft_revision },
            drafts: {
              ...latest.drafts,
              [taskId]: {
                ...latest.drafts[taskId],
                synced_version: Math.max(latest.drafts[taskId].synced_version, sent.version),
              },
            },
          }));
        }
        this.retryAfter = 0;
        this.host.patch({ error: null });
      } catch (error) {
        this.retryAfter = Date.now() + 5_000;
        if (error instanceof ApiError && error.code === 'draft_conflict') {
          this.host.patch({ conflict: true, error: 'На сервере есть более новый черновик, возможно из другой вкладки. Ваш ввод сохранён на устройстве и не заменён.' });
        } else {
          this.host.patch({
            error: `Черновик сохранён на устройстве, ожидает отправки. ${errorText(error)}`,
            accessDenied: error instanceof ApiError && [401, 404].includes(error.status),
          });
        }
      } finally {
        this.host.patch({ syncing: false });
      }
    }).finally(() => {
      this.running = null;
      const { record, conflict, error, accessDenied } = this.host.getSnapshot();
      if (record && hasDirtyDrafts(record) && !conflict && !error && !accessDenied) this.schedule();
    });
    return this.running;
  }

  async keepLocal() {
    await this.host.queue.run(async () => {
      this.host.patch({ syncing: true });
      try {
        const remote = await this.host.api.session(this.host.id);
        await this.host.update((record) => mergeSession(record, remote));
        this.host.patch({ conflict: false, error: null });
      } catch (error) {
        this.host.patch({ error: errorText(error) });
      } finally {
        this.host.patch({ syncing: false });
      }
    });
    await this.flush();
  }
}
