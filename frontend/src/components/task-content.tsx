import type { PublicTask } from '../api/types';
import { MathFormula, RichText } from './math';

export function TaskContent({ task }: { task: PublicTask }) {
  return <div className="task-content">
    <p className="task-statement"><RichText text={task.statement} /></p>
    {task.formula && <MathFormula value={task.formula} />}
    {task.table && <div className="table-scroll" role="region" aria-label="Данные условия" tabIndex={0}>
      <table><caption className="sr-only">Таблица к условию задачи</caption><thead><tr>{task.table.headers.map((header, index) => <th scope="col" key={index}><RichText text={header} /></th>)}</tr></thead>
        <tbody>{task.table.rows.map((row, index) => <tr key={index}>{row.map((cell, column) => <td key={column}><RichText text={cell} /></td>)}</tr>)}</tbody></table>
    </div>}
  </div>;
}
