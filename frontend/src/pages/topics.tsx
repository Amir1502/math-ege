import { ArrowUpRight } from 'lucide-react';
import { profileResource, progressResource, useResource } from '../app/resources';
import { EmptyState, ErrorNotice, Loading, PageHeading } from '../components/ui';
import { SlotRail } from '../components/slot-rail';

export default function TopicsPage() {
  const profile = useResource(profileResource);
  const progress = useResource(progressResource, true);
  return <>
    <PageHeading title="Темы первой части" description="От короткой теории к самостоятельному ответу." />
    {profile.loading && <Loading label="Загружаем темы" />}
    {profile.error && <ErrorNotice message={profile.error} retry={profile.retry} />}
    {profile.data && <>
      <SlotRail slots={profile.data.slots} />
      {profile.data.slots.length === 0 && <EmptyState title="Темы ещё не опубликованы">Матрица появится после загрузки экзаменационного профиля на сервер.</EmptyState>}
      <div className="topic-ledger">{profile.data.slots.map((slot) => {
        const state = progress.data?.slots.find((item) => item.number === slot.number);
        return <article className="topic-row" key={slot.id}>
          <span className="topic-row__number">{String(slot.number).padStart(2, '0')}</span>
          <div className="topic-row__body"><h2><a href={`#/topics/${slot.number}`}>{slot.title}<ArrowUpRight aria-hidden="true" /></a></h2><p>{slot.summary}</p>
            <ul className="skill-list" aria-label="Обязательные навыки">{slot.skills.map((skill) => <li key={skill.id}>{skill.title}</li>)}</ul>
          </div>
          <div className="topic-row__meta"><span className="level-label">{slot.level === 'Б' ? 'Базовый' : 'Повышенный'}</span><span>{state?.status ?? 'Нет данных'}</span><small>{slot.available_tasks} задач в демобанке</small></div>
        </article>;
      })}</div>
    </>}
    {progress.error && <p className="muted">История пока недоступна. Темы можно читать без гостевого доступа.</p>}
  </>;
}
