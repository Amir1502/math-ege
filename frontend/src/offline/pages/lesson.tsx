import { ArrowLeft, ArrowRight, Clock } from 'lucide-react';
import { MathFormula, RichText } from '../../components/math';
import { OfflineHeading, PositionRail } from './shared';
import type { Course } from './shared';

export default function LessonPage({ id, course }: { id: string; course: Course }) {
  const lesson = course.lessons.find((item) => item.id === id);
  if (!lesson) return <><OfflineHeading title="Урок не найден" /><p>В этом пакете нет урока с таким адресом. Другие уроки доступны без сети.</p><a className="button button--primary" href="#/lessons">Все уроки</a></>;
  const foundation = lesson.kind === 'foundation' || lesson.slot === 0;
  const relatedSlots = course.profile.slots.filter((slot) => foundation ? lesson.related_slot_ids?.includes(slot.id) : slot.number === lesson.slot);
  const prerequisites = course.lessons.filter((item) => lesson.prerequisite_ids?.includes(item.id));
  const siblings = course.lessons.filter((item) => item.id !== lesson.id && item.slot === lesson.slot && item.kind !== 'foundation');
  const query = new URLSearchParams({ length: '5' });
  if (relatedSlots.length) query.set('slots', relatedSlots.map((slot) => slot.number).join(','));
  if (lesson.skill_ids.length) query.set('skills', lesson.skill_ids.join(','));
  if (lesson.family_ids?.length) query.set('families', lesson.family_ids.join(','));
  const examples = [lesson.example, ...(lesson.examples ?? [])];
  const relatedTasks = course.tasks.filter((task) => lesson.practice_task_ids?.includes(task.id) || lesson.family_ids?.includes(task.family_id));

  return <>
    <a className="back-link" href={foundation ? '#/lessons' : `#/lessons?slot=${lesson.slot}`}><ArrowLeft aria-hidden="true" />К списку уроков</a>
    <OfflineHeading title={lesson.title}>{foundation ? 'Базовая тема курса' : `Номер ${lesson.slot} первой части`}. Встроенный демонстрационный материал.</OfflineHeading>
    <div className="offline-lesson-layout">
      <article className="worksheet offline-lesson-body">
        <p className="offline-reading-time"><Clock aria-hidden="true" />{lesson.minutes} мин чтения</p>
        {lesson.sections.map((section, index) => <section className="offline-theory-section" key={index}>
          <h2>{section.heading}</h2><p><RichText text={section.body} /></p>{section.formula && <MathFormula value={section.formula} />}
        </section>)}
        {examples.map((example, index) => <section className="offline-worked-example" key={index}>
          <h2>{index === 0 ? 'Разберём на примере' : 'Ещё один разбор'}</h2>
          <p><RichText text={example.statement} /></p>
          <ol className="solution-steps">{example.steps.map((step, number) => <li key={number}><RichText text={step} /></li>)}</ol>
          <p className="offline-example-answer">Ответ: <strong><RichText text={example.answer} /></strong></p>
        </section>)}
        <section className="offline-takeaway"><h2>Что стоит запомнить</h2><p><RichText text={lesson.takeaway} /></p></section>
        <a className="button button--primary offline-lesson-practice" href={`#/practice?${query}`}>Перейти к практике<ArrowRight aria-hidden="true" /></a>
      </article>
      <aside className="offline-lesson-aside">
        <section><h2>Теперь ваш ход</h2><p>Начните с пяти задач. Подсказки и решение доступны в занятии, а первый ответ остаётся в истории.</p>
          {relatedTasks.length > 0 && <p className="muted">Связанных условий в пакете: {relatedTasks.length}. Новые отбираются при начале занятия.</p>}
          <p className="muted">Чтение теории не меняет счётчик самостоятельных ответов.</p>
        </section>
        {prerequisites.length > 0 && <section><h2>Если нужна база</h2><p className="muted">Это ссылки для учёбы, не запрет на практику.</p><ul className="offline-related-links">{prerequisites.map((item) => <li key={item.id}><a className="text-link" href={`#/lessons/${encodeURIComponent(item.id)}`}>{item.title}</a></li>)}</ul></section>}
        {siblings.length > 0 && <section><h2>Другие уроки номера</h2><ul className="offline-related-links">{siblings.map((item) => <li key={item.id}><a className="text-link" href={`#/lessons/${encodeURIComponent(item.id)}`}>{item.title}</a></li>)}</ul></section>}
        <p className="offline-bottom-note muted">Курс остаётся демонстрационным. Упаковка в приложение не подтверждает предметную рецензию.</p>
      </aside>
    </div>
    <section className="offline-lesson-positions"><h2>{foundation ? 'Номера первой части' : 'Другие номера'}</h2><PositionRail course={course} active={foundation ? undefined : lesson.slot} /></section>
  </>;
}
