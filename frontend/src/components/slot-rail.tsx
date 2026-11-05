import type { Slot } from '../api/types';

export function SlotRail({ slots, active }: { slots: Slot[]; active?: number }) {
  return <nav className="slot-rail" aria-label="Структура первой части">
    {slots.map((slot) => <a key={slot.id} href={`#/topics/${slot.number}`} title={slot.title} aria-label={`Номер ${slot.number}. ${slot.title}`} aria-current={active === slot.number ? 'page' : undefined}>
      <span>{slot.number}</span>
    </a>)}
  </nav>;
}
