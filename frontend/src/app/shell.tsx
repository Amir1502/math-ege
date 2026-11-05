import { useEffect, type ReactNode } from 'react';
import { BookOpen, ChartNoAxesCombined, CircleHelp, ClipboardList, Layers, RotateCcw, Sigma, WifiOff } from 'lucide-react';
import { useOnline } from './online';
import { PwaPrompt } from '../components/pwa-prompt';

const items = [
  { path: '/', title: 'План', icon: ClipboardList },
  { path: '/topics', title: 'Темы', icon: BookOpen },
  { path: '/practice', title: 'Практика', icon: Layers },
  { path: '/review', title: 'Повторение', icon: RotateCcw },
  { path: '/progress', title: 'Прогресс', icon: ChartNoAxesCombined },
];

export function Shell({ path, children }: { path: string; children: ReactNode }) {
  const online = useOnline();
  const activePath = path.startsWith('/session') || path.startsWith('/summary') ? '/practice' : path.startsWith('/topics') ? '/topics' : path;
  useEffect(() => {
    const current = items.find((item) => item.path === activePath)?.title ?? 'Учебный тренажёр';
    document.title = `${current} | ЕГЭ Профиль 2027`;
    window.scrollTo({ top: 0, behavior: 'instant' });
    const heading = document.querySelector<HTMLElement>('h1');
    heading?.focus({ preventScroll: true });
  }, [activePath, path]);

  return <div className="app-shell">
    <a className="skip-link" href="#main-content" onClick={(event) => { event.preventDefault(); document.getElementById('main-content')?.focus(); }}>Перейти к содержанию</a>
    <aside className="sidebar">
      <a className="brand" href="#/" aria-label="ЕГЭ Профиль, главная"><span className="brand-mark"><Sigma aria-hidden="true" /></span><span>ЕГЭ Профиль<strong>Математика 2027</strong></span></a>
      <nav className="main-nav" aria-label="Главная навигация">{items.map(({ path: itemPath, title, icon: Icon }) => <a href={`#${itemPath}`} key={itemPath} aria-current={activePath === itemPath ? 'page' : undefined}><Icon aria-hidden="true" /><span>{title}</span></a>)}</nav>
      <div className="sidebar-footer"><p>Неофициальный тренажёр.<br />Первая часть, проект 2027.</p><a href="#/help"><CircleHelp aria-hidden="true" />О данных и проекте</a></div>
    </aside>
    <div className="app-main"><header className="topbar"><a className="mobile-brand" href="#/"><Sigma aria-hidden="true" />ЕГЭ Профиль</a><div className="environment-label"><span>Проект 2027</span><span>Демобанк</span></div><a className="guest-label" href="#/help">Гостевой режим<CircleHelp aria-hidden="true" /></a></header>
      {!online && <div className="offline-banner" role="status"><WifiOff aria-hidden="true" /><span>Без сети. Доступны открытые уроки и сохранённое занятие.</span></div>}
      <main id="main-content" tabIndex={-1} className="page-content">{children}</main>
      <PwaPrompt activeTask={path.startsWith('/session/')} />
      <footer className="page-footer"><span>Учебный результат, не прогноз балла ЕГЭ.</span><a href="#/help">Данные и ограничения этапа</a></footer>
    </div>
  </div>;
}
