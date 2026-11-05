import { useEffect, useRef } from 'react';
import { identity } from '../storage/identity';
import { guardAccountRequest } from './access';
import { AccountError } from './errors';

export function useAccountScope({ scope, owner }: { scope?: string; owner?: string }) {
  const lifetime = useRef({ active: true, scope, owner, guards: new Set<ReturnType<typeof guardAccountRequest>>() });
  useEffect(() => {
    const mounted = { active: true, scope, owner, guards: new Set<ReturnType<typeof guardAccountRequest>>() };
    lifetime.current = mounted;
    return () => { mounted.active = false; mounted.guards.forEach((guard) => guard.close()); mounted.guards.clear(); };
  }, [scope, owner]);

  return () => {
    const mounted = lifetime.current;
    if (!mounted.active || mounted.scope !== scope || mounted.owner !== owner) throw new AccountError(409, 'conflict');
    const guard = guardAccountRequest(identity);
    if ((scope !== undefined && scope !== `${guard.epoch}:${guard.owner ?? 'none'}`)
      || (owner !== undefined && owner !== guard.owner)) {
      guard.close();
      throw new AccountError(409, 'conflict');
    }
    mounted.guards.add(guard);
    return {
      current: () => mounted.active && guard.current(),
      close: () => { mounted.guards.delete(guard); guard.close(); },
    };
  };
}
