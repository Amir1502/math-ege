import { ArrowLeft, BookOpen, Clock } from 'lucide-react';
import { lessonResource, profileResource, useResource } from '../app/resources';
import { ActionLink, ErrorNotice, Loading, PageHeading } from '../components/ui';
import { RichText, MathFormula } from '../components/math';
import { SlotRail } from '../components/slot-rail';

export default function LessonPage({ slot }: { slot: number }) {
  const lesson = useResource(lessonResource(slot));
  const profile = useResource(profileResource);
  return <>
    <a className="back-link" href="#/topics"><ArrowLeft aria-hidden="true" />Все темы</a>
    <PageHeading title={lesson.data?.title ?? `Тема № ${slot}`} description={`Номер ${slot} первой части`} />
    {lesson.loading && <Loading label="Загружаем урок" />}
    {lesson.error && <ErrorNotice message={lesson.data ? `Показана ранее открытая версия урока. ${lesson.error}` : lesson.error} retry={lesson.retry} />}
    {lesson.cached && <p className="notice">Урок открыт из памяти устройства. Для новых задач нужна сеть.</p>}
    {lesson.data && <div className="lesson-layout">
      <article className="worksheet lesson-body">
        <div className="lesson-meta"><span><BookOpen aria-hidden="true" />Короткая теория</span><span><Clock aria-hidden="true" />{lesson.data.minutes} мин чтения</span></div>
        {lesson.data.sections.map((section, index) => <section className="theory-section" key={index}><h2>{section.heading}</h2><p><RichText text={section.body} /></p>{section.formula && <MathFormula value={section.formula} />}</section>)}
        <section className="worked-example"><h2>Разберём на примере</h2><p><RichText text={lesson.data.example.statement} /></p><ol className="solution-steps">{lesson.data.example.steps.map((step, index) => <li key={index}><RichText text={step} /></li>)}</ol><p className="example-answer">Ответ: <strong>{lesson.data.example.answer}</strong></p></section>
        <section className="takeaway"><h2>Что стоит запомнить</h2><p><RichText text={lesson.data.takeaway} /></p></section>
        <ActionLink href={`/practice?slots=${slot}`} primary>Перейти к практике</ActionLink>
      </article>
      <aside className="lesson-aside"><h2>Теперь ваш ход</h2><p>Начните с пяти задач. В практике доступны три подсказки и отдельное полное решение.</p><p className="muted">Чтение теории не увеличивает число самостоятельных ответов.</p><div className="demo-note">Материал демонстрационный. Независимая предметная проверка не заявляется.</div></aside>
    </div>}
    {profile.data && <section className="structure"><h2>Другие номера</h2><SlotRail slots={profile.data.slots} active={slot} /></section>}
  </>;
}
