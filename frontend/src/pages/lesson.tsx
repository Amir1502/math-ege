import { ArrowLeft, BookOpen, Clock } from 'lucide-react';
import { lessonResource, profileResource, useResource } from '../app/resources';
import { ActionLink, ErrorNotice, Loading, PageHeading } from '../components/ui';
import { RichText, MathFormula } from '../components/math';
import { SlotRail } from '../components/slot-rail';
import { curriculumResource } from '../app/curriculum';

export default function LessonPage({ slot = 0, lessonId }: { slot?: number; lessonId?: string }) {
  const profile = useResource(profileResource);
  const lesson = useResource(lessonResource(slot, lessonId));
  const curriculum = useResource(curriculumResource);
  const current = lesson.data;
  const foundation = current?.kind === 'foundation';
  const related = profile.data?.slots.filter((item) => foundation ? current?.related_slot_ids?.includes(item.id) : item.number === (current?.slot ?? slot)) ?? [];
  const query = new URLSearchParams({ slots: related.map((item) => item.number).join(',') || String(current?.slot ?? slot) });
  if (current?.family_ids?.length) query.set('families', current.family_ids.join(','));
  const prerequisiteIds = new Set(current?.prerequisite_ids);
  const prerequisites = curriculum.data?.lessons.filter((item) => prerequisiteIds.has(item.id)) ?? [];
  const siblings = curriculum.data?.lessons.filter((item) => item.kind === 'exam' && item.slot === (current?.slot ?? slot)) ?? [];
  return <>
    <a className="back-link" href="#/topics"><ArrowLeft aria-hidden="true" />Все темы</a>
    <PageHeading title={current?.title ?? (slot ? `Тема № ${slot}` : 'Урок')} description={foundation ? 'База для дальнейшей практики' : `Номер ${current?.slot ?? slot} первой части`} />
    {lesson.loading && <Loading label="Загружаем урок" />}
    {lesson.error && <ErrorNotice message={lesson.data ? `Показана ранее открытая версия урока. ${lesson.error}` : lesson.error} retry={lesson.retry} />}
    {lesson.cached && <p className="notice">Урок открыт из памяти устройства. Для новых задач нужна сеть.</p>}
    {lesson.data && <div className="lesson-layout">
      <article className="worksheet lesson-body">
        <div className="lesson-meta"><span><BookOpen aria-hidden="true" />Короткая теория</span><span><Clock aria-hidden="true" />{lesson.data.minutes} мин чтения</span></div>
        {lesson.data.sections.map((section, index) => <section className="theory-section" key={index}><h2>{section.heading}</h2><p><RichText text={section.body} /></p>{section.formula && <MathFormula value={section.formula} />}</section>)}
        {[lesson.data.example, ...(lesson.data.examples ?? [])].map((example, index) => <section className="worked-example" key={index}><h2>{index ? 'Ещё один разбор' : 'Разберём на примере'}</h2><p><RichText text={example.statement} /></p><ol className="solution-steps">{example.steps.map((step, number) => <li key={number}><RichText text={step} /></li>)}</ol><p className="example-answer">Ответ: <strong><RichText text={example.answer} /></strong></p></section>)}
        <section className="takeaway"><h2>Что стоит запомнить</h2><p><RichText text={lesson.data.takeaway} /></p></section>
        <ActionLink href={`/practice?${query}`} primary>{foundation ? 'Попробовать в экзаменационных задачах' : 'Перейти к практике этого типа'}</ActionLink>
      </article>
      <aside className="lesson-aside"><h2>Теперь ваш ход</h2><p>Начните с пяти задач. В практике доступны три подсказки и отдельное полное решение.</p><p className="muted">Чтение теории не увеличивает число самостоятельных ответов.</p>
        {lesson.data.review_status !== 'reviewed' && <div className="demo-note">Материал демонстрационный. Независимая предметная проверка не заявляется.</div>}
        {prerequisites.length > 0 && <section className="lesson-links"><h2>Если нужна база</h2><p>Рекомендации, не обязательные условия доступа.</p><ul>{prerequisites.map((item) => <li key={item.id}><a href={`#/lessons/${encodeURIComponent(item.id)}`}>{item.title}</a></li>)}</ul></section>}
        {siblings.length > 1 && <section className="lesson-links"><h2>Уроки этого номера</h2><ul>{siblings.map((item) => <li key={item.id}><a href={`#/lessons/${encodeURIComponent(item.id)}`} aria-current={item.id === lesson.data?.id ? 'page' : undefined}>{item.title}</a></li>)}</ul></section>}
        {curriculum.error && <ErrorNotice message={curriculum.error} retry={curriculum.retry} />}
      </aside>
    </div>}
    {profile.data && <section className="structure"><h2>{foundation ? 'Где пригодится' : 'Другие номера'}</h2><SlotRail slots={foundation ? related : profile.data.slots} active={current?.slot ?? slot} /></section>}
  </>;
}
