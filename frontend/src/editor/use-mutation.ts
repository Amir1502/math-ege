import { useMemo, useSyncExternalStore } from 'react';
import { EditorMutationQueue } from './mutation-queue';

export function useEditorMutation(actorId: string, maxBytes: number) {
  const queue = useMemo(() => new EditorMutationQueue(actorId, maxBytes), [actorId, maxBytes]);
  const state = useSyncExternalStore(queue.subscribe, queue.getSnapshot);
  return { ...state, locked: state.busy || state.uncertain, run: queue.run, retry: queue.retry };
}
export type EditorMutation = ReturnType<typeof useEditorMutation>;
