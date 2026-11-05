import { ArrowUpRight, CornerDownRight } from 'lucide-react';
import { profileResource, useResource } from '../app/resources';
import { sessionPath } from '../app/router';
import { ActionLink, ErrorNotice, GuestNote, Loading, PageHeading } from '../components/ui';
import { SlotRail } from '../components/slot-rail';
import { useLearningDashboard, useLocalActivePractice, useLocalAssessmentContinuation, usePracticeProgress } from '../extras/hooks';
import { TimePlanChooser } from '../extras/time-plan';
import { dueReviews, familyPracticePath, skillTitle } from '../extras/view-models';
import { formatDate } from '../utils/format';
import '../styles/extras.css';

export default function PlanPage() {
  const profile = useResource(profileResource);
  const progress = usePracticeProgress();
  const learning = useLearningDashboard();
  const localActive = useLocalActivePractice();
  const localAssessment = useLocalAssessmentContinuation();
  const active = progress.data?.active_session_id ?? localActive;
  const activeAssessment = progress.data?.active_assessment_id ?? localAssessment;
  const due = learning.data ? dueReviews(learning.data.reviews) : [];

  return <>
    <PageHeading title="План занятий" description="Первая часть. По одному понятному шагу." />
    {active && <div className="resume-strip"><div><strong>У вас есть начатое занятие</strong><p>Вернитесь к условию и сохранённому ответу.</p></div><ActionLink href={sessionPath(active)}>Продолжить</ActionLink></div>}
    {activeAssessment && <div className="resume-strip"><div><strong>У вас есть сохранённый вариант</strong><p>Откройте диагностику или пробник, чтобы продолжить или проверить состояние.</p></div><ActionLink href={`/assessment/${encodeURIComponent(activeAssessment)}`}>Открыть вариант</ActionLink></div>}
    {profile.loading && <Loading label="Загружаем экзаменационный профиль" />}
    {profile.error && <ErrorNotice message={profile.error} retry={profile.retry} />}
    {profile.data && <>
      <div className="plan-layout">
        <section className="worksheet plan-sheet" aria-labelledby="today-heading">
           <div className="sheet-heading"><h2 id="today-heading">Практика в вашем темпе</h2><CornerDownRight aria-hidden="true" /></div>
           <p className="lead">Выберите время. План объединит новые задачи, слабые навыки и повторение.</p>
           <TimePlanChooser />
        </section>
        <aside className="plan-aside" aria-label="Об этом этапе">
          <div className="profile-note"><span className="profile-year">{profile.data.year}</span><strong>{profile.data.status === 'draft' ? 'Проект экзаменационного профиля' : 'Учебный экзаменационный профиль'}</strong><p>{profile.data.verification_note}</p></div>
          <div className="bank-note"><h2>{profile.data.demo_mode ? 'Демонстрационный банк' : 'Учебный банк'}</h2><p>{profile.data.bank_size} экземпляров.{profile.data.demo_mode && ' Материалы остаются демонстрационными до независимой предметной рецензии.'}</p><a className="text-link" href="#/help">О материалах <ArrowUpRight aria-hidden="true" /></a></div>
          <div className="learning-assessment-entry"><h2>Проверить себя</h2><p>Диагностика и пробник первой части: 13 задач, разбор после завершения.</p><a className="text-link" href="#/assessment">Диагностика и пробник <ArrowUpRight aria-hidden="true" /></a></div>
        </aside>
      </div>
      <section className="structure" aria-labelledby="structure-heading"><div className="section-heading"><h2 id="structure-heading">Карта первой части</h2><span>{profile.data.slots.length} номеров</span></div><SlotRail slots={profile.data.slots} /><p>Каждая ячейка открывает тему и короткий урок. Это структура, не оценка готовности.</p></section>
    </>}
    {learning.loading && !learning.data && <Loading label="Составляем рекомендации" />}
    {learning.error && <ErrorNotice message={learning.error} retry={learning.retry} />}
    {learning.data && <section className="learning-plan-next" aria-labelledby="plan-next-heading">
      <div className="section-heading"><h2 id="plan-next-heading">Следующий шаг</h2><a className="text-link" href="#/review?tab=repeat">К повторению<ArrowUpRight aria-hidden="true" /></a></div>
      <div className="learning-next-columns">
        <div><h3>К повторению сейчас</h3>{due.length ? <ul className="learning-next-list">{due.slice(0, 3).map((review) => {
          const path = familyPracticePath(review.slot, review.family_id);
          return <li key={`${review.skill_id}:${review.family_id}`}><strong>{path ? <a className="text-link" href={`#${path}`}>{skillTitle(learning.data!, review.skill_id)}</a> : skillTitle(learning.data!, review.skill_id)}</strong><span>{review.slot === null ? 'Прежний профиль' : `Номер ${review.slot}`} · <time dateTime={review.due_at}>{formatDate(review.due_at)}</time></span></li>;
        })}</ul> : <p className="muted">На сейчас повторений нет. Можно решить новые задачи или посмотреть будущие даты.</p>}</div>
        <div><h3>Навыки для внимания</h3>{learning.data.weak_skills.length ? <ul className="learning-next-list">{learning.data.weak_skills.slice(0, 3).map((skill) => <li key={skill.id}><a className="text-link" href={`#/practice?slots=${skill.slot}&skills=${encodeURIComponent(skill.id)}&selection=mixed`}>{skill.title}</a><span>Номер {skill.slot}</span></li>)}</ul> : <p className="muted">Пока нет отдельной подборки слабых навыков. Новые самостоятельные ответы уточнят план.</p>}</div>
      </div>
      {learning.data.recommendation && <p className="learning-recommendation">{learning.data.recommendation}</p>}
    </section>}
    {progress.error && <ErrorNotice message={`Не удалось проверить историю. ${progress.error}`} retry={progress.retry} />}
    <GuestNote />
  </>;
}
