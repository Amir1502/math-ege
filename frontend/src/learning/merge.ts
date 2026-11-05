import type { LearningSession } from '../api/types';
import { createRecord, type SessionRecord } from './model';

/** Merge server facts without replacing a locally edited answer or the local navigation position. */
export function mergeSession(local: SessionRecord, remote: LearningSession): SessionRecord {
  if (remote.status === 'active' && (local.session.status === 'completed' || remote.draft_revision < local.session.draft_revision)) return local;
  const incoming = createRecord(remote);
  for (const [id, draft] of Object.entries(local.drafts)) {
    if (!incoming.drafts[id]) continue;
    if (draft.version > draft.synced_version) {
      incoming.drafts[id] = { ...draft, active_seconds: Math.max(draft.active_seconds, incoming.drafts[id].active_seconds) };
    } else {
      incoming.drafts[id] = {
        ...incoming.drafts[id],
        active_seconds: Math.max(draft.active_seconds, incoming.drafts[id].active_seconds),
        version: draft.version,
        synced_version: draft.synced_version,
      };
    }
  }
  const attempts = new Map(local.session.attempts.map((attempt) => [attempt.id, attempt]));
  for (const attempt of remote.attempts) attempts.set(attempt.id, attempt);
  const help = { ...local.session.help };
  for (const [id, remoteHelp] of Object.entries(remote.help)) {
    const hints = new Map((help[id]?.hints ?? []).map((hint) => [hint.level, hint]));
    for (const hint of remoteHelp.hints) hints.set(hint.level, hint);
    help[id] = {
      hints: [...hints.values()].sort((a, b) => a.level - b.level),
      solution: remoteHelp.solution ?? help[id]?.solution ?? null,
    };
  }
  return {
    ...local,
    drafts: incoming.drafts,
    current_index: Math.min(local.current_index, Math.max(0, remote.tasks.length - 1)),
    session: {
      ...remote,
      draft_revision: Math.max(local.session.draft_revision, remote.draft_revision),
      attempts: [...attempts.values()],
      help,
    },
    pending_finish: remote.status === 'completed' ? false : local.pending_finish,
    saved_at: Date.now(),
  };
}
