import { useCallback, useEffect, useRef, useState } from 'react';
import type { MouseEvent } from 'react';
import { BookOpen, ChartNoAxesColumnIncreasing, CircleHelp, PencilLine } from 'lucide-react';
import { loadOfflineCourse } from './content';
import { OfflineRuntime } from './practice';
import type { OfflineCourse } from './types';
import PracticePage from './pages/practice';
import SessionPage from './pages/session';
import LessonsPage from './pages/lessons';
import LessonPage from './pages/lesson';
import ProgressPage from './pages/progress';
import SummaryPage from './pages/summary';
import HelpPage from './pages/help';
import { OfflineFailure, OfflineHeading, OfflineLoading } from './pages/shared';
import type { Failure, LeaveGuard, RegisterLeaveGuard, RuntimeState } from './pages/shared';
import { failure } from './pages/operations';

type Loaded = { course: OfflineCourse; runtime: OfflineRuntime; state: RuntimeState | null; storageError: Failure | null };
type Route = { hash: string; section: 'practice' | 'lessons' | 'progress' | 'help' | 'missing'; view: 'list' | 'session' | 'summary' | 'lesson'; id: string; query: URLSearchParams };

function readRoute(): Route {
  const hash = window.location.hash || '#/practice';
  const value = hash.slice(1);
  const split = value.indexOf('?');
  const path = split < 0 ? value : value.slice(0, split);
  const query = new URLSearchParams(split < 0 ? '' : value.slice(split + 1));
  if (path === '/' || path === '/practice' || path === '') return { hash, section: 'practice', view: 'list', id: '', query };
  if (path === '/lessons') return { hash, section: 'lessons', view: 'list', id: '', query };
  if (path === '/progress') return { hash, section: 'progress', view: 'list', id: '', query };
  if (path === '/help') return { hash, section: 'help', view: 'list', id: '', query };
  const match = /^\/(session|summary|lessons)\/([^/]+)$/.exec(path);
  if (match) {
    try {
      const id = decodeURIComponent(match[2]);
      return { hash, section: match[1] === 'lessons' ? 'lessons' : 'practice', view: match[1] === 'lessons' ? 'lesson' : match[1] as 'session' | 'summary', id, query };
    } catch { /* Malformed hash IDs use the not-found screen without changing stored data. */ }
  }
  return { hash, section: 'missing', view: 'list', id: '', query };
}

const navigation = [
  { section: 'practice', label: 'Практика', Icon: PencilLine },
  { section: 'lessons', label: 'Уроки', Icon: BookOpen },
  { section: 'progress', label: 'Прогресс', Icon: ChartNoAxesColumnIncreasing },
  { section: 'help', label: 'О приложении', Icon: CircleHelp },
] as const;

export default function OfflineApp() {
  const [route, setRoute] = useState(readRoute);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [bootError, setBootError] = useState<Failure | null>(null);
  const [bootKey, setBootKey] = useState(0);
  const [checkingStorage, setCheckingStorage] = useState(false);
  const ready = loaded !== null;
  const acceptedHash = useRef(route.hash);
  const leaveGuard = useRef<LeaveGuard | null>(null);
  const navigationRevision = useRef(0);

  useEffect(() => {
    let cancelled = false;
    void loadOfflineCourse().then(async (course) => {
      const runtime = new OfflineRuntime(course);
      if (cancelled) { void runtime.close(); return; }
      let state: RuntimeState | null = null;
      let storageError: Failure | null = null;
      try { state = await runtime.state(); }
      catch (error) { storageError = failure(error); }
      if (cancelled) { void runtime.close(); return; }
      setLoaded({ course, runtime, state, storageError });
      setBootError(null);
    }).catch((error: unknown) => {
      if (!cancelled) setBootError(failure(error));
    });
    return () => { cancelled = true; };
  }, [bootKey]);

  const refreshState = useCallback(async () => {
    if (!loaded || checkingStorage) return;
    setCheckingStorage(true);
    try {
      const state = await loaded.runtime.state();
      setLoaded((current) => current && { ...current, state, storageError: null });
    } catch (error) {
      setLoaded((current) => current && { ...current, storageError: failure(error) });
    } finally {
      setCheckingStorage(false);
    }
  }, [loaded, checkingStorage]);

  const registerLeaveGuard: RegisterLeaveGuard = useCallback((guard: LeaveGuard) => {
    leaveGuard.current = guard;
    return () => { if (leaveGuard.current === guard) leaveGuard.current = null; };
  }, []);

  useEffect(() => {
    const accept = async () => {
      const revision = ++navigationRevision.current;
      const requested = readRoute();
      if (requested.hash === acceptedHash.current) return;
      const guard = leaveGuard.current;
      const allowed = !guard || await guard();
      if (revision !== navigationRevision.current) return;
      if (allowed) {
        acceptedHash.current = requested.hash;
        setRoute(requested);
      } else {
        window.history.replaceState(null, '', acceptedHash.current);
      }
    };
    const changed = () => { void accept(); };
    window.addEventListener('hashchange', changed);
    return () => window.removeEventListener('hashchange', changed);
  }, []);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const heading = document.querySelector<HTMLHeadingElement>('.offline-main h1');
      window.scrollTo({ top: 0, behavior: 'instant' });
      document.title = `${heading?.textContent ?? 'ЕГЭ Профиль 2027'} · На устройстве`;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [route.hash, ready]);

  const focusedHash = useRef(route.hash);
  useEffect(() => {
    if (focusedHash.current === route.hash) return;
    focusedHash.current = route.hash;
    const frame = window.requestAnimationFrame(() => {
      document.querySelector<HTMLHeadingElement>('.offline-main h1')?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [route.hash]);

  const skipToMain = (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    document.getElementById('offline-main')?.focus();
  };

  let page;
  if (!loaded) {
    page = bootError ? <><OfflineHeading title="Курс пока недоступен" /><OfflineFailure error={bootError} title="Не удалось открыть встроенный курс"
      retry={() => { setBootError(null); setBootKey((key) => key + 1); }} /><p>История не удалялась. Перезапуск не требует очистки данных приложения.</p></>
      : <><OfflineHeading title="Практика на устройстве" /><OfflineLoading label="Открываем встроенные уроки и задачи" /></>;
  } else if (route.view === 'session') {
    page = <SessionPage key={route.id} id={route.id} course={loaded.course} runtime={loaded.runtime} registerLeaveGuard={registerLeaveGuard} />;
  } else if (route.view === 'summary') {
    page = <SummaryPage key={route.id} id={route.id} course={loaded.course} runtime={loaded.runtime} />;
  } else if (route.view === 'lesson') {
    page = <LessonPage key={route.id} id={route.id} course={loaded.course} />;
  } else if (route.section === 'practice') {
    page = <PracticePage key={route.hash} course={loaded.course} runtime={loaded.runtime} deviceState={loaded.state}
      storageError={loaded.storageError} retryStorage={() => void refreshState()} checkingStorage={checkingStorage} query={route.query} />;
  } else if (route.section === 'lessons') {
    page = <LessonsPage key={route.hash} course={loaded.course} query={route.query} />;
  } else if (route.section === 'progress') {
    page = <ProgressPage course={loaded.course} runtime={loaded.runtime} />;
  } else if (route.section === 'help') {
    page = <HelpPage course={loaded.course} />;
  } else {
    page = <><OfflineHeading title="Такого экрана нет" /><p>Ссылка не соответствует разделам приложения. История на устройстве не менялась.</p>
      <a className="button button--primary" href="#/practice">К практике</a></>;
  }

  return <div className="offline-shell">
    <a className="offline-skip-link" href="#offline-main" onClick={skipToMain}>Перейти к содержанию</a>
    <header className="offline-brand">
      <a href="#/practice" aria-label="ЕГЭ Профиль 2027. Практика">ЕГЭ Профиль <span>2027</span></a>
      <p>Демонстрационный проект</p>
    </header>
    <nav className="offline-nav" aria-label="Разделы приложения">
      {navigation.map(({ section, label, Icon }) => <a key={section} href={`#/${section}`}
        aria-current={route.section === section ? 'page' : undefined}><Icon aria-hidden="true" /><span>{label}</span></a>)}
    </nav>
    <div className="offline-device-mark"><span>Хранение на устройстве</span><span>Без облачной синхронизации</span></div>
    <main id="offline-main" className="offline-main" tabIndex={-1}>{page}</main>
  </div>;
}
