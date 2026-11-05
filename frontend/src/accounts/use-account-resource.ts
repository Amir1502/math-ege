import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { identity } from '../storage/identity';
import { accountErrorText } from './errors';

export function useAccountResource<T>(load: () => Promise<T>, scope: string) {
  const access = useSyncExternalStore(identity.subscribe, identity.getSnapshot, identity.getSnapshot);
  const available = scope === 'auth-config' || (access.ready && !access.changing && access.error === null
    && scope === `${access.epoch}:${access.value?.id ?? 'none'}`);
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<{ scope: string; data: T | null; loading: boolean; error: string | null }>({
    scope, data: null, loading: true, error: null,
  });
  useEffect(() => {
    let ignore = false;
    setState({ scope, data: null, loading: true, error: null });
    void load().then(
      (data) => { if (!ignore) setState({ scope, data, loading: false, error: null }); },
      (error: unknown) => { if (!ignore) setState({ scope, data: null, loading: false, error: accountErrorText(error) }); },
    );
    return () => { ignore = true; };
  }, [load, scope, revision, available]);
  const retry = useCallback(() => setRevision((value) => value + 1), []);
  const replace = useCallback((data: T) => setState({ scope, data, loading: false, error: null }), [scope]);
  return {
    data: available && state.scope === scope ? state.data : null,
    loading: !available || state.scope !== scope || state.loading,
    error: state.scope === scope ? state.error : null,
    retry, replace,
  };
}
