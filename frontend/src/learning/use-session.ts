import { useEffect, useSyncExternalStore } from 'react';
import { sessionController, type SessionController } from './session-controller';
import { ActiveClock } from './active-clock';

export function useSession(id: string) {
  const controller = sessionController(id);
  const snapshot = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  useEffect(() => { void controller.load(); }, [controller]);
  return { controller, ...snapshot };
}

export function useActiveClock(controller: SessionController, taskId: string | undefined, enabled: boolean) {
  useEffect(() => {
    if (!taskId || !enabled) return;
    const clock = new ActiveClock(controller.getSnapshot().record?.drafts[taskId]?.active_seconds ?? 0);
    const save = () => controller.recordTime(taskId, clock.seconds());
    const visibility = () => {
      if (document.visibilityState === 'visible') clock.start();
      else { clock.pause(); save(); }
    };
    const leave = () => { clock.pause(); save(); };
    visibility();
    const interval = setInterval(save, 500);
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('pagehide', leave);
    window.addEventListener('pageshow', visibility);
    return () => {
      leave();
      clearInterval(interval);
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('pagehide', leave);
      window.removeEventListener('pageshow', visibility);
    };
  }, [controller, taskId, enabled]);
}
