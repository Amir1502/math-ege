import { useCallback, useEffect, useRef, useState } from 'react';
import { EditorError, errorText } from './adapters';

export function useEditorResource<T>(load: (signal: AbortSignal) => Promise<T>, key: string) {
  const [generation, setGeneration] = useState(0);
  const active = useRef<AbortController | null>(null);
  const [state, setState] = useState<{ key: string; data: T | null; loading: boolean; error: EditorError | null }>({ key, data: null, loading: true, error: null });
  const retry = useCallback(() => setGeneration(value => value + 1), []);
  const replace = useCallback((data: T) => {
    active.current?.abort();
    setState({ key, data, loading: false, error: null });
  }, [key]);
  useEffect(() => {
    const controller = new AbortController();
    active.current = controller;
    setState({ key, data: null, loading: true, error: null });
    load(controller.signal).then(data => {
      if (!controller.signal.aborted) setState({ key, data, loading: false, error: null });
    }).catch(error => {
      if (!controller.signal.aborted) setState({
        key, data: null, loading: false,
        error: error instanceof EditorError ? error : new EditorError(errorText(error)),
      });
    });
    return () => controller.abort();
  }, [load, key, generation]);
  const current = state.key === key ? state : { key, data: null, loading: true, error: null };
  return { ...current, retry, replace };
}
