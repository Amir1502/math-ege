import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import type { Figure } from '../src/api/types';
import { TaskFigure } from '../src/components/task-figure';
import { projectFigure } from '../src/utils/figure';

const figure: Figure = {
  description: 'Квадрат со стороной 2.', x_min: -1, x_max: 3, y_min: -1, y_max: 3, axes: true,
  lines: [{ points: [{ x: 0, y: 0 }, { x: 2, y: 0 }, { x: 2, y: 2 }] }],
  circles: [{ center: { x: 1, y: 1 }, radius: 1 }], labels: [{ x: 1, y: 0, text: '<script>alert(1)</script>' }],
};

describe('data-only mathematical figures', () => {
  it('preserves unit scale on both axes and reverses only the vertical coordinate', () => {
    const { point, radius } = projectFigure(figure);
    const origin = point({ x: 0, y: 0 });
    expect(point({ x: 1, y: 0 }).x - origin.x).toBe(radius(1));
    expect(origin.y - point({ x: 0, y: 1 }).y).toBe(radius(1));
  });
  it('renders explicit shapes and escaped labels, never executable imported markup', () => {
    const html = renderToStaticMarkup(createElement(TaskFigure, { figure }));
    expect(html).toContain('<polyline');
    expect(html).toContain('<circle');
    expect(html).toContain('aria-labelledby');
    expect(html).toContain('&lt;script&gt;');
    expect(html).not.toContain('<script>');
  });
});
