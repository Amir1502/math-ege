import { useState } from 'react';
import { Button } from '../components/ui';
import type { EditorProfile } from './types';

export function ProfileReference({ profile }: { profile: EditorProfile }) {
  const [selected, setSelected] = useState(profile.slots[0]?.id);
  const slot = profile.slots.find(item => item.id === selected);
  return <details className="editor-disclosure editor-reference">
    <summary>Позиции и стабильные ID текущего профиля</summary>
    <p><strong>{profile.title}</strong><br /><code>{profile.id}</code>{profile.revision && <> / <code>{profile.revision}</code></>}</p>
    <div className="editor-slot-map" role="group" aria-label="Позиции экзаменационного профиля">
      {profile.slots.map(item => <Button key={item.id} aria-pressed={selected === item.id}
        aria-label={`Номер ${item.number}: ${item.title}`} onClick={() => setSelected(item.id)}>{item.number}</Button>)}
    </div>
    {slot && <div className="editor-slot-detail" aria-live="polite">
      <h2>№ {slot.number}. {slot.title}</h2>
      <dl className="editor-ledger"><div><dt>slot_id</dt><dd><code>{slot.id}</code></dd></div>
        <div><dt>lesson_id</dt><dd><code>{slot.lesson_id}</code></dd></div>
        <div><dt>Навыки</dt><dd><ul>{slot.skills.map(skill => <li key={skill.id}><code>{skill.id}</code><br />{skill.title}</li>)}</ul></dd></div>
      </dl>
    </div>}
    <p className="muted">При перенумерации сохраните ID навыков и укажите новые привязки задач и уроков в одном пакете публикации.</p>
  </details>;
}
