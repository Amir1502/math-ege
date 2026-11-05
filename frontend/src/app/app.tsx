import { lazy, Suspense, useEffect, useSyncExternalStore } from 'react';
import { useRoute } from './router';
import { Shell } from './shell';
import { ActionLink, EmptyState, ErrorNotice, Loading, PageHeading } from '../components/ui';
import { identity } from '../storage/identity';
import PlanPage from '../pages/plan';

const TopicsPage = lazy(() => import('../pages/topics'));
const LessonPage = lazy(() => import('../pages/lesson'));
const PracticePage = lazy(() => import('../pages/practice'));
const SessionPage = lazy(() => import('../pages/session'));
const SummaryPage = lazy(() => import('../pages/summary'));
const ReviewPage = lazy(() => import('../pages/review'));
const ProgressPage = lazy(() => import('../pages/progress'));
const HelpPage = lazy(() => import('../pages/help'));
const AccountPage = lazy(() => import('../pages/account'));
const AssessmentPage = lazy(() => import('../pages/assessment'));
const EditorPage = lazy(() => import('../pages/editor'));

export default function App() {
  const access = useSyncExternalStore(identity.subscribe, identity.getSnapshot);
  useEffect(() => { void identity.refresh(); }, []);
  if (!access.ready || access.changing) return <Shell path="/"><Loading label={access.changing ? 'Сохраняем состояние перед сменой доступа' : 'Восстанавливаем доступ к вашим занятиям'} /></Shell>;
  return <RoutedApp key={access.epoch} identityError={access.error} />;
}

function RoutedApp({ identityError }: { identityError: string | null }) {
  const route = useRoute();
  let page;
  if (route.path === '/') page = <PlanPage />;
  else if (route.path === '/topics') page = <TopicsPage />;
  else if (/^\/topics\/\d+$/.test(route.path)) page = <LessonPage key={route.path} slot={Number(route.path.split('/')[2])} />;
  else if (/^\/lessons\/[^/]+$/.test(route.path)) page = <LessonPage key={route.path} lessonId={decodeURIComponent(route.path.split('/')[2])} />;
  else if (route.path === '/practice') page = <PracticePage key={route.location} query={route.query} />;
  else if (/^\/session\/[^/]+$/.test(route.path)) page = <SessionPage key={route.path} id={decodeURIComponent(route.path.split('/')[2])} />;
  else if (/^\/summary\/[^/]+$/.test(route.path)) page = <SummaryPage key={route.path} id={decodeURIComponent(route.path.split('/')[2])} />;
  else if (route.path === '/review') page = <ReviewPage />;
  else if (route.path === '/progress') page = <ProgressPage />;
  else if (route.path === '/help') page = <HelpPage />;
  else if (route.path === '/account') page = <AccountPage />;
  else if (route.path === '/editor') page = <EditorPage />;
  else if (route.path === '/auth/complete') page = <AccountPage completion />;
  else if (route.path === '/assessment') page = <AssessmentPage ownerId={identity.current() ?? undefined} />;
  else if (/^\/assessment\/[^/]+$/.test(route.path)) page = <AssessmentPage key={route.path} ownerId={identity.current() ?? undefined} id={decodeURIComponent(route.path.split('/')[2])} />;
  else page = <><PageHeading title="Страница не найдена" /><EmptyState title="Такого раздела нет" action={<ActionLink href="/" primary>К плану занятий</ActionLink>}>Ссылка не соответствует ни одному экрану тренажёра.</EmptyState></>;
  return <Shell path={route.path}>{identityError && <ErrorNotice message={identityError} retry={() => void identity.refresh()} />}<Suspense fallback={<Loading label="Открываем раздел" />}>{page}</Suspense></Shell>;
}
