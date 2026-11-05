import { ArrowUpRight } from 'lucide-react';
import { ActionLink, EmptyState } from '../components/ui';
import { formatDate, formatDuration } from '../utils/format';
import { LearningPagination } from './pagination';
import { originalProfileLabel } from './view-models';
import type { LearningDashboard, SlotEvidence } from './types';

export function MasteryLedger({ slots, dashboard }: { slots: SlotEvidence[]; dashboard: LearningDashboard | null }) {
  return <section className="coverage-section learning-coverage" aria-labelledby="coverage-heading">
    <div className="section-heading"><h2 id="coverage-heading">Номера и навыки</h2><a className="text-link" href="#/topics">К темам<ArrowUpRight aria-hidden="true" /></a></div>
    <p className="muted">Статусы описывают данные тренажёра. Они не гарантируют результат на экзамене.</p>
    {dashboard && <p className="microcopy">Для карты учтено самостоятельных первых ответов: {dashboard.independent_total}, из них верных: {dashboard.independent_correct}. Алгоритм: {dashboard.algorithm_version}.</p>}
    <div className="coverage-ledger">{slots.map((slot) => <details key={slot.slot_id} className="learning-slot">
      <summary className="coverage-row">
        <span className="slot-number">{slot.number}</span>
        <span><strong>{slot.title}</strong><small>Обязательные навыки с самостоятельным успехом: {slot.covered_skills} из {slot.total_skills}</small></span>
        <span className="coverage-result"><strong>{slot.correct} / {slot.attempts}</strong><small className={`learning-mastery ${slot.status === 'Освоено' ? 'learning-mastery--established' : ''}`}>{slot.status}</small></span>
      </summary>
      <div className="learning-slot-details">
        <p className="microcopy">{slot.correct} верных из {slot.attempts} независимых ответов. Числовые варианты одного шаблона не считаются разными семействами.</p>
        {slot.skills.length > 0 ? <table className="learning-skill-table"><caption>Самостоятельные ответы по обязательным навыкам</caption>
          <thead><tr><th scope="col">Навык</th><th scope="col">Верно / ответов</th></tr></thead>
          <tbody>{slot.skills.map((skill) => <tr key={skill.id}><th scope="row">{skill.title}</th><td>{skill.correct} / {skill.attempts}</td></tr>)}</tbody>
        </table> : <p className="muted">Подробности по навыкам появятся после загрузки карты обучения.</p>}
        <a className="text-link" href={`#/topics/${slot.number}`}>Открыть тему<ArrowUpRight aria-hidden="true" /></a>
      </div>
    </details>)}</div>
    <details className="learning-method"><summary>Что означают статусы?</summary><dl>
      <div><dt>Нет данных</dt><dd>Ещё нет независимых ответов по номеру.</dd></div>
      <div><dt>Изучаю</dt><dd>Ответы уже есть; самостоятельное решение пока требует закрепления.</dd></div>
      <div><dt>Закрепляю</dt><dd>Есть серия самостоятельных успехов, но выполнены ещё не все условия освоения.</dd></div>
      <div><dt>Освоено</dt><dd>Достаточно независимых ответов в разные дни, охвачены разные семейства и каждый обязательный навык, пройдено отложенное повторение без помощи.</dd></div>
    </dl><p className="microcopy">Статус может вернуться к закреплению после новых ошибок. Подсказки, исправления и просмотр теории не создают новое независимое достижение.</p></details>
  </section>;
}

export function AssessmentHistoryPanel({ dashboard }: { dashboard: LearningDashboard }) {
  return <section className="history-section learning-assessments" aria-labelledby="assessment-history-heading">
    <div className="section-heading"><h2 id="assessment-history-heading">Диагностика и пробники</h2><a className="text-link" href="#/assessment">Новая проверка<ArrowUpRight aria-hidden="true" /></a></div>
    <p className="muted">Результаты первой части от 0 до 13. Сравнивайте их с учётом времени и исходного профиля.</p>
    {dashboard.assessment_history.length ? <table className="learning-results-table" role="table">
      <caption>Завершённые проверки с открытыми результатами. Это не полный тестовый балл ЕГЭ.</caption>
      <thead><tr><th scope="col">Дата и режим</th><th scope="col">Результат</th><th scope="col">Время</th><th scope="col">Исходный профиль</th></tr></thead>
      <tbody>{dashboard.assessment_history.map((assessment) => <tr key={assessment.id}>
        <th scope="row"><a className="text-link" href={`#/assessment/${encodeURIComponent(assessment.id)}`}>{assessment.mode === 'exam' ? 'Пробник первой части' : 'Диагностика'}<ArrowUpRight aria-hidden="true" /></a><time dateTime={assessment.snapshot_at}>{formatDate(assessment.snapshot_at)}</time></th>
        <td data-label="Результат"><strong>{assessment.score} / 13</strong><small>Пропуски: {assessment.skipped}. Ошибки формата: {assessment.format_errors}.</small></td>
        <td data-label="Время"><span>По таймеру: {formatDuration(assessment.elapsed_seconds)}</span><small>Активное: {formatDuration(assessment.active_seconds)}</small></td>
        <td data-label="Исходный профиль">{originalProfileLabel(assessment.profile)}</td>
      </tr>)}</tbody>
    </table> : <EmptyState title="Завершённых проверок пока нет" action={<ActionLink href="/assessment">Открыть диагностику и пробник</ActionLink>}>Результат, время и исходный профиль появятся после завершения и открытия разбора.</EmptyState>}
    <LearningPagination dashboard={dashboard} collection="assessment_history" href={(offset) => `/progress?offset=${offset}`} />
  </section>;
}

export function LearningNotifications({ dashboard, excludedTotal = dashboard?.excluded_total ?? 0 }: { dashboard: LearningDashboard | null; excludedTotal?: number }) {
  const notifications = dashboard?.notifications ?? [];
  // viora-allow: aria-live-missing This is a persistent history section; the page loading/error regions announce request state.
  if (!notifications.length && !excludedTotal) return null;
  return <section className="learning-notifications" aria-labelledby="learning-notifications-heading">
    <h2 id="learning-notifications-heading">Изменения в учебных данных</h2>
    {excludedTotal > 0 && <p>Из показателей освоения исключено записей: {excludedTotal}. Исходная история сохранена.</p>}
    {notifications.length > 0 && <ul>{notifications.map((notification) => <li key={notification.id}><p>{notification.message}</p><time className="microcopy" dateTime={notification.created_at}>{formatDate(notification.created_at)}</time></li>)}</ul>}
    {dashboard && <LearningPagination dashboard={dashboard} collection="notifications" href={(offset) => `/progress?offset=${offset}`} />}
  </section>;
}
