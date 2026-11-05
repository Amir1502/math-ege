import { useEffect, useState, useSyncExternalStore } from 'react';
import { registerSW } from 'virtual:pwa-register';
import { Download, RefreshCw, X } from 'lucide-react';
import { storage } from '../storage/database';
import { Button } from './ui';

type InstallPromptEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }> };

// Worker events belong to this document, not the shell replaced during identity bootstrap.
let workerState = { needRefresh: false, offlineReady: false };
const workerListeners = new Set<() => void>();
function patchWorkerState(change: Partial<typeof workerState>) {
  workerState = { ...workerState, ...change };
  workerListeners.forEach((listener) => listener());
}
const workerSnapshot = () => workerState;
const subscribeWorker = (listener: () => void) => {
  workerListeners.add(listener);
  return () => { workerListeners.delete(listener); };
};
const updateServiceWorker = registerSW({
  immediate: true,
  onNeedRefresh: () => patchWorkerState({ needRefresh: true }),
  onOfflineReady: () => patchWorkerState({ offlineReady: true }),
});

export function PwaPrompt({ activeTask }: { activeTask: boolean }) {
  const { needRefresh, offlineReady } = useSyncExternalStore(subscribeWorker, workerSnapshot);
  const [install, setInstall] = useState<InstallPromptEvent | null>(null);
  const [updateBlocked, setUpdateBlocked] = useState(false);
  useEffect(() => {
    const handler = (event: Event) => { event.preventDefault(); setInstall(event as InstallPromptEvent); };
    window.addEventListener('beforeinstallprompt', handler);
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  const update = async () => {
    const id = await storage.active().catch(() => null);
    const record = id ? await storage.session(id).catch(() => null) : null;
    if (activeTask || record?.session.status === 'active') {
      setUpdateBlocked(true);
      return;
    }
    await updateServiceWorker(true);
  };
  const dismiss = () => { patchWorkerState({ needRefresh: false, offlineReady: false }); setInstall(null); setUpdateBlocked(false); };
  if (!needRefresh && !offlineReady && !install) return null;
  return <aside className="pwa-notice" aria-label="Установка и обновление приложения"><div><strong>{needRefresh ? 'Доступна новая версия' : offlineReady ? 'Оболочка доступна без сети' : 'Можно установить на устройство'}</strong><p>{needRefresh ? (activeTask || updateBlocked ? 'Обновление отложено. Сначала завершите активное занятие: страница не будет перезагружена автоматически.' : 'Обновите страницу, когда будет удобно. Во время активной серии обновление не запускается.') : 'Открытые уроки и черновики доступны без сети. Для проверки ответа нужен сервер.'}</p><div className="row-actions">{needRefresh && !activeTask && !updateBlocked && <Button onClick={() => void update()}><RefreshCw aria-hidden="true" />Обновить</Button>}{install && <Button onClick={() => { void install.prompt().then(() => setInstall(null)); }}><Download aria-hidden="true" />Установить</Button>}<Button variant="quiet" onClick={dismiss}><X aria-hidden="true" />Позже</Button></div></div></aside>;
}
