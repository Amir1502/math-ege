import { useState } from 'react';
import { ArrowRight, BookOpen, Search } from 'lucide-react';
import { Button } from '../../components/ui';
import { OfflineHeading, PositionRail } from './shared';
import type { Course } from './shared';

export default function LessonsPage({ course, query }: { course: Course; query: URLSearchParams }) {
  const [search, setSearch] = useState(query.get('q') ?? '');
  const slotValue = Number(query.get('slot'));
  const selected = course.profile.slots.find((slot) => slot.number === slotValue);
  const text = search.trim().toLocaleLowerCase('ru-RU');
  const matching = course.lessons.filter((lesson) => {
    const slotMatch = !selected || lesson.slot === selected.number || lesson.related_slot_ids?.includes(selected.id);
    const titleMatch = !text || `${lesson.title} ${lesson.takeaway}`.toLocaleLowerCase('ru-RU').includes(text);
    return slotMatch && titleMatch;
  });
  const foundation = matching.filter((lesson) => lesson.kind === 'foundation' || lesson.slot === 0);
  const groups = course.profile.slots.map((slot) => ({ slot, lessons: matching.filter((lesson) => lesson.kind !== 'foundation' && lesson.slot === slot.number) })).filter((group) => group.lessons.length > 0);
  const other = matching.filter((lesson) => lesson.kind !== 'foundation' && lesson.slot !== 0 && !course.profile.slots.some((slot) => slot.number === lesson.slot));

  const lessonRows = (lessons: Course['lessons']) => <ul className="offline-lesson-list">
    {lessons.map((lesson) => <li key={lesson.id}><a href={`#/lessons/${encodeURIComponent(lesson.id)}`}>
      <span><strong>{lesson.title}</strong><span className="offline-lesson-meta">Теория и разборы · {lesson.minutes} мин чтения</span></span>
      <ArrowRight aria-hidden="true" />
    </a></li>)}
  </ul>;

  return <>
    <OfflineHeading title="Уроки">Все {course.lessons.length} уроков включены в приложение. Сеть и предварительное открытие не нужны.</OfflineHeading>
    <PositionRail course={course} active={selected?.number} />
    <div className="offline-lessons-toolbar">
      <form role="search" className="offline-search" onSubmit={(event) => {
        event.preventDefault();
        const next = new URLSearchParams();
        if (selected) next.set('slot', String(selected.number));
        if (search.trim()) next.set('q', search.trim());
        const queryString = next.toString();
        window.location.hash = `/lessons${queryString ? `?${queryString}` : ''}`;
      }}>
        <label htmlFor="lesson-search">Найти урок</label>
        <div><input id="lesson-search" name="q" type="search" autoComplete="off" value={search} onChange={(event) => setSearch(event.target.value)} />
          <Button type="submit" aria-label="Найти урок"><Search aria-hidden="true" /></Button>
        </div>
      </form>
      <div className="offline-lessons-count"><p>{selected ? `№ ${selected.number}. ${selected.title}` : 'Все номера и базовые темы'}</p>
        <p className="muted">Найдено уроков: {matching.length} из {course.lessons.length}.</p>
        {(selected || text) && <a className="text-link" href="#/lessons">Показать все уроки</a>}
      </div>
    </div>
    {matching.length === 0 ? <section className="empty-state"><h2>По этому запросу уроков нет</h2><p>Попробуйте более короткое название или откройте весь список.</p><a className="button button--primary" href="#/lessons">Все уроки</a></section>
      : <div className="offline-lesson-groups">
        {foundation.length > 0 && <section className="offline-lesson-group"><h2><BookOpen aria-hidden="true" />Базовые темы</h2>{lessonRows(foundation)}</section>}
        {groups.map(({ slot, lessons }) => <section className="offline-lesson-group" key={slot.number}><h2><span className="slot-number">{slot.number}</span>{slot.title}</h2>{lessonRows(lessons)}</section>)}
        {other.length > 0 && <section className="offline-lesson-group"><h2>Другие темы курса</h2>{lessonRows(other)}</section>}
      </div>}
    <p className="offline-bottom-note muted">Чтение урока не добавляет самостоятельный ответ. Материалы демонстрационные; независимая предметная рецензия не заявляется.</p>
  </>;
}
