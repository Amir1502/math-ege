import { AccountError } from './errors';
import type { AccountIdentityAccess, AccountRequestAccess } from './types';

const conflict = () => new AccountError(409, 'conflict');

export function captureAccountAccess(identity: AccountIdentityAccess): AccountRequestAccess {
  const snapshot = identity.getSnapshot();
  if (!snapshot.ready || snapshot.changing || snapshot.error !== null || !snapshot.value?.id) throw conflict();
  return Object.freeze({ owner: snapshot.value.id, epoch: snapshot.epoch });
}

export function guardAccountRequest(identity: AccountIdentityAccess, options: {
  bootstrap?: boolean;
  transition?: AccountRequestAccess;
} = {}) {
  const snapshot = identity.getSnapshot();
  // Cached, unverified identity may be observed for a bootstrap read, never used as an owner pin.
  const owner = snapshot.ready && snapshot.error === null ? snapshot.value?.id ?? null : null;
  const initialOwner = snapshot.value?.id ?? null;
  const kind = snapshot.value?.kind ?? null;
  const epoch = snapshot.epoch;
  const ready = snapshot.ready;
  const changing = snapshot.changing;
  if (snapshot.error !== null || (changing && !options.transition)
    || (!options.bootstrap && (!ready || !owner))
    || (options.transition && (options.transition.owner !== owner || options.transition.epoch !== epoch))) throw conflict();

  const controller = new AbortController();
  let active = true;
  const current = () => {
    const next = identity.getSnapshot();
    if (next.ready !== ready || next.changing !== changing || next.error !== null
      || next.epoch !== epoch || (next.value?.id ?? null) !== initialOwner || (next.value?.kind ?? null) !== kind) {
      active = false;
      controller.abort();
    }
    return active;
  };
  // Latch every intervening transition, including one that finishes with the same owner and epoch.
  const unsubscribe = identity.subscribe(current);
  return {
    owner, kind, epoch, signal: controller.signal, current,
    check: () => { if (!current()) throw conflict(); },
    close: () => { unsubscribe(); active = false; },
  };
}
