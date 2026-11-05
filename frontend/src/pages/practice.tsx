import { profileResource, progressResource, useResource } from '../app/resources';
import { ActionLink, ErrorNotice, GuestNote, Loading, PageHeading } from '../components/ui';
import { StartPanel } from '../components/start-panel';
import { sessionPath } from '../app/router';

export default function PracticePage({ selection }: { selection: string | null }) {
  const profile = useResource(profileResource);
  const progress = useResource(progressResource, true);
  const selected = selection?.split(',').map(Number).filter((number) => profile.data?.slots.some((slot) => slot.number === number));
  return <>
    <PageHeading title="Практика" description="Один номер или смешанная серия. Без таймера на оценку." />
    {progress.data?.active_session_id && <div className="resume-strip"><p>Начатое занятие остаётся в истории. Можно продолжить его вместо нового.</p><ActionLink href={sessionPath(progress.data.active_session_id)}>Продолжить</ActionLink></div>}
    {profile.loading && <Loading label="Загружаем настройки практики" />}
    {profile.error && <ErrorNotice message={profile.error} retry={profile.retry} />}
    {profile.data && <div className="practice-layout"><section className="worksheet"><h2>Соберите своё занятие</h2><StartPanel key={selection} profile={profile.data} expanded initialSlots={selected} /></section><aside className="practice-aside"><h2>Как устроена серия</h2><ol className="plain-steps"><li>Получите новые экземпляры из выбранных номеров.</li><li>Отправьте ответ или откройте помощь.</li><li>После ошибки исправьте ответ. Первый результат сохранится.</li><li>Завершите серию и посмотрите честный итог.</li></ol><p className="demo-note">Демобанк ограничен. Уже выданная задача не повторяется 30 дней.</p><GuestNote compact /></aside></div>}
  </>;
}
