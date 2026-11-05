import { identity } from '../storage/identity';
import { accountApi } from './api';
import { createAccountFlow } from './flow';
import { accountLink } from './fragment';

export const accountFlow = createAccountFlow(accountApi, identity, accountLink);

// A transition may remount React. Keep setup only in memory, scoped to its account,
// and erase it when that account leaves or the document is put in the back/forward cache.
if (typeof window !== 'undefined') {
  let previous = identity.current();
  identity.subscribe(() => {
    const next = identity.current();
    if (next !== previous) { previous = next; accountFlow.forgetEnrollment(); }
  });
  const leave = () => { accountFlow.forgetEnrollment(); accountFlow.discardCompletion(); };
  window.addEventListener('pagehide', leave);
  window.addEventListener('hashchange', () => {
    const path = window.location.hash.slice(1).split('?')[0];
    if (path !== '/account') accountFlow.forgetEnrollment();
    if (path !== '/account' && path !== '/auth/complete') accountFlow.discardCompletion();
  });
}
