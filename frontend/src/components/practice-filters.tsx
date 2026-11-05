import type { Profile, StartBody } from '../api/types';
import type { Curriculum } from '../app/curriculum';
import '../styles/practice.css';

function Choice({ label, name, selected = [], options, onChange }: {
  label: string; name: string; selected?: string[];
  options: { id: string; title: string }[]; onChange: (ids: string[]) => void;
}) {
  const known = new Set(options.map((option) => option.id));
  return <label>{label}<select name={name} value={selected.length > 1 ? '@selected' : selected[0] ?? ''} onChange={(event) => onChange(event.target.value ? [event.target.value] : [])}>
    <option value="">Все</option>
    {selected.length > 1 && <option value="@selected" disabled>Выбрано по ссылке: {selected.length}</option>}
    {selected.length === 1 && !known.has(selected[0]) && <option value={selected[0]} disabled>Сохранённый выбор: {selected[0]}</option>}
    {options.map((option) => <option key={option.id} value={option.id}>{option.title}</option>)}
  </select></label>;
}

export function PracticeFilters({ profile, curriculum, options, disabled, change }: {
  profile: Profile; curriculum?: Curriculum; options: StartBody; disabled: boolean;
  change: (value: Partial<StartBody>) => void;
}) {
  const families = curriculum?.families.filter((family) => options.slots.includes(family.slot)) ?? [];
  const skills = profile.slots.filter((slot) => options.slots.includes(slot.number)).flatMap((slot) => slot.skills);
  const expanded = Boolean(options.family_ids?.length || options.skill_ids?.length || options.target_minutes || options.until_stopped || options.repeat_task_id || options.selection === 'mixed' || options.difficulty);
  return <details className="practice-options" open={expanded || undefined}>
    <summary>Подтема, тип задачи и режим</summary>
    <fieldset disabled={disabled}>
      <legend className="sr-only">Дополнительные настройки практики</legend>
      <Choice label="Подтема" name="skill" selected={options.skill_ids} options={skills} onChange={(skill_ids) => change({ skill_ids, repeat_task_id: null })} />
      <Choice label="Тип задачи" name="family" selected={options.family_ids} options={families.map((family) => ({ id: family.id, title: `№ ${family.slot} · ${family.title}` }))} onChange={(family_ids) => change({ family_ids, repeat_task_id: null })} />
      <label>Сложность<select name="difficulty" value={options.difficulty ?? ''} onChange={(event) => change({ difficulty: event.target.value ? Number(event.target.value) as 1 | 2 | 3 : null })}><option value="">Любая сложность</option><option value="1">Базовая</option><option value="2">Средняя</option><option value="3">Повышенная</option></select></label>
      <label>Подбор<select name="selection" value={options.selection ?? 'balanced'} onChange={(event) => change({ selection: event.target.value as 'balanced' | 'mixed' })}><option value="balanced">Равномерно по номерам</option><option value="mixed">С учётом слабых мест и повторения</option></select></label>
      {options.selection === 'mixed' && <p className="microcopy">Ориентир: 50% слабых мест, 30% повторения и 20% нового. При нехватке подходящих задач состав изменится без скрытых повторов.</p>}
      <label>Ориентир по времени<select name="minutes" value={options.target_minutes ?? ''} onChange={(event) => change({ target_minutes: event.target.value ? Number(event.target.value) as 10 | 20 | 30 : null })}><option value="">Без ориентира</option>{([10, 20, 30] as const).map((minutes) => <option key={minutes} value={minutes}>{minutes} минут</option>)}</select></label>
      <label className="practice-toggle"><input type="checkbox" name="until_stopped" checked={options.until_stopped ?? false} disabled={disabled || Boolean(options.repeat_task_id)} onChange={(event) => change({ until_stopped: event.target.checked })} /><span>До остановки: добавлять следующую порцию задач в это занятие</span></label>
      {options.target_minutes && <p className="microcopy">Это ориентир, а не экзаменационный таймер. Занятие не завершится без вашего подтверждения.</p>}
    </fieldset>
  </details>;
}
