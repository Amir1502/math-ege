import type { Summary } from '../api/types';
import { formatDuration } from '../utils/format';

export function SummaryStats({ summary }: { summary: Summary }) {
  return <div className="summary-stats">
    <div className="main-stat"><span className="main-stat__value">{summary.independent_correct}<span> / {summary.independent_total}</span></span><p>первых самостоятельных ответов верны</p></div>
    <dl className="stat-ledger">
      <div><dt>С помощью</dt><dd>{summary.assisted}</dd></div>
      <div><dt>Повторных ответов</dt><dd>{summary.corrections}</dd></div>
      <div><dt>Пропущено</dt><dd>{summary.skipped}</dd></div>
      <div><dt>Активное время</dt><dd>{formatDuration(summary.active_seconds)}</dd></div>
    </dl>
  </div>;
}
