import { profileResource, progressResource, useResource } from '../app/resources';
import { ActionLink, ErrorNotice, GuestNote, Loading, PageHeading } from '../components/ui';
import { StartPanel } from '../components/start-panel';
import { sessionPath } from '../app/router';
import { curriculumResource } from '../app/curriculum';
import { practiceOptions } from '../learning/practice-options';

export default function PracticePage({ query }: { query: URLSearchParams }) {
  const profile = useResource(profileResource);
  const curriculum = useResource(curriculumResource);
  const progress = useResource(progressResource, true);
  const options = practiceOptions(query);
  return <>
    <PageHeading title="Практика" description="Один номер или смешанная серия. Без таймера на оценку." />
    {progress.data?.active_session_id && <div className="resume-strip"><p>Начатое занятие остаётся в истории. Можно продолжить его вместо нового.</p><ActionLink href={sessionPath(progress.data.active_session_id)}>Продолжить</ActionLink></div>}
    {profile.loading && <Loading label="Загружаем настройки практики" />}
    {profile.error && <ErrorNotice message={profile.error} retry={profile.retry} />}
    {curriculum.error && <ErrorNotice message={curriculum.error} retry={curriculum.retry} />}
    {profile.data && <div className="practice-layout"><section className="worksheet"><h2>Соберите своё занятие</h2><StartPanel profile={profile.data} curriculum={curriculum.data ?? undefined} expanded initialOptions={options} /></section><aside className="practice-aside"><h2>Как устроена серия</h2><ol className="plain-steps"><li>Получите новые экземпляры из выбранных номеров.</li><li>Отправьте ответ или откройте помощь.</li><li>После ошибки исправьте ответ. Первый результат сохранится.</li><li>Завершите серию и посмотрите честный итог.</li></ol><p className="demo-note">Уже выданная задача не повторяется 30 дней без вашего явного выбора.</p><GuestNote compact /></aside></div>}
  </>;
}
