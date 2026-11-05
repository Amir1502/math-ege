import { ApiError, errorText } from '../api/client';
import type { SessionHost } from './host';
import type { DraftSync } from './draft-sync';
import { answerFormatError } from './answer-format';
import { hasDirtyDrafts } from './model';
import { mergeSession } from './merge';

export class SessionMutations {
  constructor(private readonly host: SessionHost, private readonly drafts: DraftSync) {}

  async submit(skipped = false) {
    const state = this.host.getSnapshot();
    const record = state.record;
    if (!record || state.busy || record.pending_finish || record.extension_key || state.accessDenied || record.session.status !== 'active') return;
    const task = record.session.tasks[record.current_index];
    if (!task) return;
    const draft = record.drafts[task.id];
    const pending = record.pending_attempt;
    this.host.patch({ busy: 'attempt', formError: null, error: null });
    try {
      if (!pending) {
        await this.host.update((latest) => ({
          ...latest,
          pending_attempt: {
            key: crypto.randomUUID(),
            body: { task_id: task.id, answer: skipped ? '' : draft.answer, active_seconds: draft.active_seconds, skipped },
          },
        }));
      }
      await this.host.queue.run(async () => {
        const persisted = this.host.getSnapshot().record?.pending_attempt;
        if (!persisted) return;
        // Retrying also waits for a durable write; a previous storage failure must not send an unpersisted event.
        await this.host.update((latest) => latest);
        const attempt = await this.host.api.attempt(this.host.id, persisted.body, persisted.key);
        await this.host.update((latest) => ({
          ...latest,
          pending_attempt: null,
          session: {
            ...latest.session,
            attempts: latest.session.attempts.some((item) => item.id === attempt.id)
              ? latest.session.attempts
              : [...latest.session.attempts, attempt],
          },
        }));
      });
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) {
        const raw = this.host.getSnapshot().record?.pending_attempt?.body.answer ?? '';
        await this.host.update((latest) => ({ ...latest, pending_attempt: null })).catch(() => undefined);
        this.host.patch({ formError: new ApiError(error.status, error.code, answerFormatError(raw) ?? error.message, error.field) });
      } else {
        this.host.patch({
          error: `Ответ сохранён на устройстве, ожидает отправки. ${errorText(error)}`,
          accessDenied: error instanceof ApiError && [401, 404].includes(error.status),
        });
      }
    } finally {
      this.host.patch({ busy: null });
    }
  }

  async hint(level: 1 | 2 | 3) {
    await this.help(async (taskId) => {
      const hint = await this.host.api.hint(this.host.id, taskId, level);
      await this.host.update((record) => {
        const previous = record.session.help[taskId] ?? { hints: [], solution: null };
        return {
          ...record,
          session: {
            ...record.session,
            help: {
              ...record.session.help,
              [taskId]: {
                ...previous,
                hints: [...previous.hints.filter((item) => item.level !== level), hint].sort((a, b) => a.level - b.level),
              },
            },
          },
        };
      });
    });
  }

  async solution() {
    await this.help(async (taskId) => {
      const solution = await this.host.api.solution(this.host.id, taskId);
      await this.host.update((record) => ({
        ...record,
        session: {
          ...record.session,
          help: { ...record.session.help, [taskId]: { hints: record.session.help[taskId]?.hints ?? [], solution } },
        },
      }));
    });
  }

  private async help(operation: (taskId: string) => Promise<void>) {
    const { record, busy, accessDenied } = this.host.getSnapshot();
    if (!record || busy || accessDenied || record.pending_attempt || record.pending_finish || record.extension_key || record.session.status !== 'active') return;
    const task = record.session.tasks[record.current_index];
    if (!task) return;
    this.host.patch({ busy: 'help', error: null });
    try {
      await this.host.queue.run(() => operation(task.id));
    } catch (error) {
      this.host.patch({ error: `Не удалось открыть помощь. ${errorText(error)}` });
    } finally {
      this.host.patch({ busy: null });
    }
  }

  async finish() {
    const { record, busy, conflict, accessDenied } = this.host.getSnapshot();
    if (!record || busy || conflict || accessDenied || record.pending_attempt || record.extension_key || record.session.status !== 'active') return;
    this.host.patch({ busy: 'finish', error: null });
    try {
      await this.host.update((latest) => ({
        ...latest,
        finish_key: latest.finish_key ?? crypto.randomUUID(),
        pending_finish: true,
      }));
      await this.drafts.flush();
      const latest = this.host.getSnapshot();
      if (!latest.record || hasDirtyDrafts(latest.record) || latest.conflict) {
        this.host.patch({ error: latest.error ?? 'Сначала нужно отправить сохранённые черновики. Повторите завершение после восстановления связи.' });
        return;
      }
      await this.host.queue.run(async () => {
        const key = this.host.getSnapshot().record?.finish_key;
        if (!key) return;
        const remote = await this.host.api.finish(this.host.id, key);
        await this.host.update((local) => mergeSession(local, remote));
      });
    } catch (error) {
      this.host.patch({ error: `Завершение ожидает подтверждения сервера. ${errorText(error)}` });
    } finally {
      this.host.patch({ busy: null });
    }
  }

  async extend() {
    const { record, busy, conflict, accessDenied } = this.host.getSnapshot();
    if (!record || busy || conflict || accessDenied || record.pending_attempt || record.pending_finish || record.session.status !== 'active' || !record.session.options?.until_stopped) return;
    this.host.patch({ busy: 'extend', error: null });
    try {
      await this.host.update((latest) => ({
        ...latest, extension_key: latest.extension_key ?? crypto.randomUUID(),
        extension_start: latest.extension_key ? latest.extension_start : latest.session.tasks.length,
      }));
      await this.drafts.flush();
      const state = this.host.getSnapshot();
      if (!state.record || hasDirtyDrafts(state.record) || state.conflict || state.accessDenied) return;
      await this.host.queue.run(async () => {
        const current = this.host.getSnapshot().record;
        if (!current?.extension_key) return;
        const remote = await this.host.api.extend(this.host.id, current.extension_key);
        await this.host.update((local) => ({
          ...mergeSession(local, remote), extension_key: null,
          current_index: Math.min(current.extension_start ?? current.session.tasks.length, remote.tasks.length - 1),
        }));
      });
    } catch (error) {
      if (error instanceof ApiError && !error.retryable) await this.host.update((latest) => ({ ...latest, extension_key: null })).catch(() => undefined);
      this.host.patch({ error: `Не удалось продолжить серию. ${errorText(error)}` });
    } finally {
      this.host.patch({ busy: null });
    }
  }
}
