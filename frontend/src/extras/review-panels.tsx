import { ArrowRight, BookOpen } from 'lucide-react';
import { ActionLink } from '../components/ui';
import { TaskContent } from '../components/task-content';
import { RichText } from '../components/math';
import { formatDate } from '../utils/format';
import { TaskAnnotations } from './task-annotations';
import { annotationValues, currentTaskSlot, entryDescription, familyPracticePath, originalProfileLabel, skillTitle } from './view-models';
import type { Favourite, JournalEntry, LearningDashboard, SavedAnnotation, ScheduledReview } from './types';

export function ReviewTask({ item, entry, annotations, dashboard }: {
  item: Favourite;
  entry: JournalEntry | null;
  annotations: SavedAnnotation[] | null;
  dashboard: LearningDashboard;
}) {
  const { task, session_id: sessionId } = item;
  const attempt = entry?.attempt;
  const currentSlot = currentTaskSlot(task, dashboard);
  const analogue = familyPracticePath(currentSlot, task.family_id);

  return <details className="mistake-row learning-review-task">
    <summary>
      <span className="topic-row__number">{String(task.slot).padStart(2, '0')}</span>
      <span><strong>{task.title}</strong><small>{entry ? entryDescription(entry) : 'Сохранено в избранном'}{attempt && <> · {formatDate(attempt.created_at)}</>}</small>
        {(entry?.manual || entry?.not_understood) && <span className="learning-entry-flags">{entry.manual && <span>Добавлено вручную</span>}{entry.not_understood && <span>Не понимаю тему</span>}</span>}
      </span>
      <BookOpen aria-hidden="true" />
    </summary>
    <div className="mistake-row__body">
      <h3>Исходное условие</h3>
      <p className="microcopy">Номер {task.slot} в исходном занятии. Редакция задачи: {task.revision}. {originalProfileLabel(item.profile)}.</p>
      <TaskContent task={task} />
      {attempt ? <>
        <dl className="answer-comparison">
          <div><dt>{attempt.first_attempt && attempt.independent ? 'Ваш первый самостоятельный ответ' : 'Ваш ответ в этой записи'}</dt><dd>{attempt.skipped ? 'Пропуск' : attempt.raw_answer || 'Нет ответа'}</dd></div>
          <div><dt>Эталон</dt><dd>{attempt.expected_answer}</dd></div>
        </dl>
        {(attempt.assisted || !attempt.first_attempt) && <p className="microcopy">{attempt.assisted && 'Ответ с помощью. '}{!attempt.first_attempt && 'Повторный ответ. '}Он не считается новым самостоятельным достижением.</p>}
        <h3>Разбор</h3>
        <ol className="solution-steps">{attempt.solution.map((step, index) => <li key={index}><RichText text={step} /></li>)}</ol>
      </> : <p className="notice">Разбор не загружен в этой записи. Здесь доступно исходное условие и ваши отметки.</p>}
      <div className="row-actions">
        {currentSlot !== null && <a className="button button--secondary" href={`#/topics/${currentSlot}`}><BookOpen aria-hidden="true" />Открыть теорию</a>}
        {analogue && <a className="button button--secondary" href={`#${analogue}`}>Решить новый аналог<ArrowRight aria-hidden="true" /></a>}
      </div>
      <p className="microcopy">{analogue
        ? 'Аналог подбирается из того же семейства с другими данными. Немедленное решение после разбора не заменяет отложенное повторение.'
        : 'Этот навык не сопоставлен с текущим профилем. Исходная запись сохранена; подбор аналога пока недоступен.'}</p>
      {annotations ? <TaskAnnotations sessionId={sessionId} taskId={task.id} values={annotationValues(annotations, sessionId, task.id)} />
        : <p className="microcopy">Ваши отметки будут доступны после загрузки. Если произошла ошибка, повторите запрос вверху страницы.</p>}
    </div>
  </details>;
}

export function ReviewQueue({ reviews, dashboard }: { reviews: ScheduledReview[]; dashboard: LearningDashboard }) {
  return <ol className="learning-review-queue">{reviews.map((review) => {
    const path = familyPracticePath(review.slot, review.family_id);
    const due = review.overdue || Date.parse(review.due_at) <= Date.now();
    return <li key={`${review.skill_id}:${review.family_id}`}>
      <div><h3>{skillTitle(dashboard, review.skill_id)}</h3>
        <p>{review.slot === null ? 'Позиция прежнего профиля' : `Номер ${review.slot}`}. {due ? 'К повторению' : 'Следующее повторение'}: <time dateTime={review.due_at}>{formatDate(review.due_at)}</time>.</p>
        <p className="microcopy">Интервал в днях: {review.interval_days}. Другой экземпляр того же семейства.</p>
      </div>
      {path ? <ActionLink href={path}>{due ? 'Повторить навык' : 'Повторить раньше'}</ActionLink> : <span className="muted">В текущем профиле нет этого номера</span>}
    </li>;
  })}</ol>;
}
