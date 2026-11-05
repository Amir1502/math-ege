import { useEffect, useSyncExternalStore } from 'react';
import { assessmentController } from './runtime';

export function useAssessment(ownerId: string, id: string, deviceId: string) {
  const controller = assessmentController(ownerId, id, deviceId);
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  useEffect(() => {
    void controller.load();
    return () => {
      controller.setVisible(false);
      void controller.persist().catch(() => undefined);
      void controller.flush();
    };
  }, [controller]);
  useEffect(() => {
    const visibility = () => {
      controller.setVisible(document.visibilityState === 'visible' && !state.readOnly);
      if (document.visibilityState === 'visible') {
        controller.tick();
        if (controller.getSnapshot().record?.view.status !== 'completed') void controller.refresh();
      }
    };
    controller.setVisible(document.visibilityState === 'visible' && !state.readOnly);
    document.addEventListener('visibilitychange', visibility);
    return () => { controller.setVisible(false); document.removeEventListener('visibilitychange', visibility); };
  }, [controller, state.readOnly]);
  return { controller, ...state };
}
