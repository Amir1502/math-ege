import { useId, useState } from 'react';
import type { Figure } from '../api/types';
import { Button } from './ui';
import { projectFigure } from '../utils/figure';

export function TaskFigure({ figure }: { figure: Figure }) {
  const label = useId();
  const [enlarged, setEnlarged] = useState(false);
  const { point, radius } = projectFigure(figure);
  const origin = point({ x: 0, y: 0 });
  return <figure className="task-figure">
    <div className="figure-scroll" role="region" aria-label="Рисунок к условию" tabIndex={0}>
      <svg viewBox="0 0 560 360" role="img" aria-labelledby={label} className={enlarged ? 'is-enlarged' : ''}>
        <title id={label}>{figure.description}</title>
        {figure.axes && <g className="figure-axes">
          {figure.y_min <= 0 && figure.y_max >= 0 && <line x1="32" x2="528" y1={origin.y} y2={origin.y} />}
          {figure.x_min <= 0 && figure.x_max >= 0 && <line x1={origin.x} x2={origin.x} y1="32" y2="328" />}
        </g>}
        <g className="figure-shapes">
          {figure.lines.map((line, index) => <polyline key={index} points={line.points.map((value) => { const p = point(value); return `${p.x},${p.y}`; }).join(' ')} strokeDasharray={line.dashed ? '6 5' : undefined} />)}
          {figure.circles.map((circle, index) => { const center = point(circle.center); return <circle key={index} cx={center.x} cy={center.y} r={radius(circle.radius)} />; })}
        </g>
        <g className="figure-labels">{figure.labels.map((value, index) => { const p = point(value); return <text key={index} x={p.x} y={p.y}>{value.text}</text>; })}</g>
      </svg>
    </div>
    <figcaption>{figure.description}</figcaption>
    <Button variant="quiet" aria-pressed={enlarged} onClick={() => setEnlarged(!enlarged)}>{enlarged ? 'Обычный размер рисунка' : 'Увеличить рисунок'}</Button>
  </figure>;
}
