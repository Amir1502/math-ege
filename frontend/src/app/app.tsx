import { lazy, Suspense } from 'react';
import { useRoute } from './router';
import { Shell } from './shell';
import { ActionLink, EmptyState, Loading, PageHeading } from '../components/ui';
import PlanPage from '../pages/plan';

const TopicsPage = lazy(() => import('../pages/topics'));
const LessonPage = lazy(() => import('../pages/lesson'));
const PracticePage = lazy(() => import('../pages/practice'));
const SessionPage = lazy(() => import('../pages/session'));
const SummaryPage = lazy(() => import('../pages/summary'));
const ReviewPage = lazy(() => import('../pages/review'));
const ProgressPage = lazy(() => import('../pages/progress'));
const HelpPage = lazy(() => import('../pages/help'));

export default function App() {
  const route = useRoute();
  let page;
  if (route.path === '/') page = <PlanPage />;
  else if (route.path === '/topics') page = <TopicsPage />;
  else if (/^\/topics\/\d+$/.test(route.path)) page = <LessonPage key={route.path} slot={Number(route.path.split('/')[2])} />;
  else if (route.path === '/practice') page = <PracticePage key={route.location} selection={route.query.get('slots')} />;
  else if (/^\/session\/[^/]+$/.test(route.path)) page = <SessionPage key={route.path} id={decodeURIComponent(route.path.split('/')[2])} />;
  else if (/^\/summary\/[^/]+$/.test(route.path)) page = <SummaryPage key={route.path} id={decodeURIComponent(route.path.split('/')[2])} />;
  else if (route.path === '/review') page = <ReviewPage />;
  else if (route.path === '/progress') page = <ProgressPage />;
  else if (route.path === '/help') page = <HelpPage />;
  else page = <><PageHeading title="Страница не найдена" /><EmptyState title="Такого раздела нет" action={<ActionLink href="/" primary>К плану занятий</ActionLink>}>Ссылка не соответствует ни одному экрану тренажёра.</EmptyState></>;
  return <Shell path={route.path}><Suspense fallback={<Loading label="Открываем раздел" />}>{page}</Suspense></Shell>;
}
