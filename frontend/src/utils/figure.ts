import type { Figure } from '../api/types';

export function projectFigure(figure: Figure) {
  const width = figure.x_max - figure.x_min;
  const height = figure.y_max - figure.y_min;
  if (!(width > 0 && height > 0 && Number.isFinite(width) && Number.isFinite(height))) throw new Error('Некорректные границы рисунка.');
  const scale = Math.min(496 / width, 296 / height);
  const left = (560 - width * scale) / 2;
  const top = (360 - height * scale) / 2;
  return {
    point: ({ x, y }: { x: number; y: number }) => ({ x: left + (x - figure.x_min) * scale, y: top + (figure.y_max - y) * scale }),
    radius: (value: number) => value * scale,
  };
}
