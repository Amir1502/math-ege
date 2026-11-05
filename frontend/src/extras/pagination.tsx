import type { DashboardCollection, LearningDashboard } from './types';

export function LearningPagination({ dashboard, collection, href }: {
  dashboard: LearningDashboard;
  collection: DashboardCollection;
  href: (offset: number) => string;
}) {
  const { offset, limit, totals } = dashboard.pagination;
  const total = totals[collection] ?? dashboard[collection].length;
  if (total <= limit && offset === 0) return null;
  return <nav className="learning-pagination" aria-label="Страницы учебных записей">
    <p>Показано {dashboard[collection].length} из {total} записей.</p>
    <div className="row-actions">
      {offset > 0 && <a className="button button--secondary" href={`#${href(Math.max(0, offset - limit))}`}>Предыдущие</a>}
      {offset + limit < total && <a className="button button--secondary" href={`#${href(offset + limit)}`}>Следующие</a>}
    </div>
  </nav>;
}
