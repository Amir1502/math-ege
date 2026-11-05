import { ArrowUpRight, CornerDownRight } from 'lucide-react';
import { profileResource, progressResource, useResource } from '../app/resources';
import { useEffect, useState } from 'react';
import { storage } from '../storage/database';
import { sessionPath } from '../app/router';
import { ActionLink, ErrorNotice, GuestNote, Loading, PageHeading } from '../components/ui';
import { StartPanel } from '../components/start-panel';
import { SlotRail } from '../components/slot-rail';

export default function PlanPage() {
  const profile = useResource(profileResource);
  const progress = useResource(progressResource, true);
  const [localActive, setLocalActive] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    void storage.active().then(async (id) => {
      if (!id) return;
      const record = await storage.session(id);
      if (alive && record?.session.status === 'active') setLocalActive(id);
    }).catch(() => undefined);
    return () => { alive = false; };
  }, []);
  const active = progress.data?.active_session_id ?? localActive;

  return <>
    <PageHeading title="План занятий" description="Первая часть. По одному понятному шагу." />
    {active && <div className="resume-strip"><div><strong>У вас есть начатое занятие</strong><p>Вернитесь к условию и сохранённому ответу.</p></div><ActionLink href={sessionPath(active)}>Продолжить</ActionLink></div>}
    {profile.loading && <Loading label="Загружаем экзаменационный профиль" />}
    {profile.error && <ErrorNotice message={profile.error} retry={profile.retry} />}
    {profile.data && <>
      <div className="plan-layout">
        <section className="worksheet plan-sheet" aria-labelledby="today-heading">
          <div className="sheet-heading"><h2 id="today-heading">Немного практики.<br />Больше ясности.</h2><CornerDownRight aria-hidden="true" /></div>
          <p className="lead">Выберите посильную серию. Решайте, разбирайте ошибки и продолжайте в своём темпе.</p>
          <StartPanel profile={profile.data} />
        </section>
        <aside className="plan-aside" aria-label="Об этом этапе">
          <div className="profile-note"><span className="profile-year">{profile.data.year}</span><strong>Проект экзаменационного профиля</strong><p>Неофициальный учебный тренажёр. Структура ещё не объявлена окончательной.</p></div>
          <div className="bank-note"><h2>Демонстрационный банк</h2><p>{profile.data.bank_size} авторских экземпляров. Это не проверенный стартовый банк и не полное покрытие навыков.</p><a className="text-link" href="#/help">Границы первого этапа <ArrowUpRight aria-hidden="true" /></a></div>
        </aside>
      </div>
      <section className="structure" aria-labelledby="structure-heading"><div className="section-heading"><h2 id="structure-heading">Карта первой части</h2><span>{profile.data.slots.length} номеров</span></div><SlotRail slots={profile.data.slots} /><p>Каждая ячейка открывает тему и короткий урок. Это структура, не оценка готовности.</p></section>
    </>}
    {progress.error && <ErrorNotice message={`Не удалось проверить историю. ${progress.error}`} retry={progress.retry} />}
    <GuestNote />
  </>;
}
