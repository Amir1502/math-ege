import { identity, type IdentityManager } from '../storage/identity';

/** A cached identity is not permission to read a private learning dashboard. */
export function confirmedLearningOwner(manager: Pick<IdentityManager, 'getSnapshot' | 'current'> = identity): string | null {
  const state = manager.getSnapshot();
  return state.ready && !state.changing && !state.error ? manager.current() : null;
}
