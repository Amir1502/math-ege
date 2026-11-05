import { MathFormula, RichText } from '../components/math';
import { TaskContent } from '../components/task-content';
import { decodeLesson, decodeProfile, strings } from './adapters';
import type { JsonValue, Preview, WorkedExample } from './types';

function Example({ example }: { example: WorkedExample }) {
  return <div className="editor-worked-example"><p><RichText text={example.statement} /></p>
    <ol>{example.steps.map((step, index) => <li key={index}><RichText text={step} /></li>)}</ol>
    <p>Ответ: <strong>{example.answer}</strong></p>
  </div>;
}

function TextList({ value }: { value: JsonValue | undefined }) {
  return Array.isArray(value) ? <ul>{value.filter(item => typeof item === 'string').map((item, index) => <li key={index}><RichText text={String(item)} /></li>)}</ul> : null;
}

export function ContentPreview({ preview }: { preview: Preview }) {
  if (preview.kind === 'task' && preview.task) return <>
    <div className="editor-mobile-preview">
      <p className="muted">№ {preview.task.slot}. {preview.task.topic}</p><h4>{preview.task.title}</h4>
      <TaskContent task={preview.task} />
      {preview.task.rounding && <p><RichText text={preview.task.rounding.instruction} /></p>}
    </div>
    <details className="editor-disclosure"><summary>Эталон и помощь для рецензента</summary>
      <p>Ответ: <strong>{String(preview.payload.answer ?? '')}</strong></p>
      <h4>Решение</h4><TextList value={preview.payload.solution} />
      <h4>Подсказки</h4><TextList value={preview.payload.hints} />
    </details>
  </>;
  if (preview.kind === 'lesson') {
    const lesson = decodeLesson(preview.payload);
    return <div className="editor-mobile-preview"><h4>{lesson.title}</h4>
      {lesson.sections.map((section, index) => <section key={index}><h5>{section.heading}</h5><p><RichText text={section.body} /></p>{section.formula && <MathFormula value={section.formula} />}</section>)}
      <section><h5>Разобранный пример</h5><Example example={lesson.example} />{lesson.examples.map((example, index) => <Example example={example} key={index} />)}</section>
      <section><h5>Что стоит запомнить</h5><p><RichText text={lesson.takeaway} /></p></section>
    </div>;
  }
  if (preview.kind === 'profile') {
    const profile = decodeProfile(preview.payload);
    return <div className="editor-mobile-preview"><h4>{profile.title}</h4>
      <p>{profile.status === 'draft' ? 'Проект профиля' : 'Утверждённый профиль'}. {profile.year} год.</p>
      <ol className="editor-profile-list">{profile.slots.map(slot => <li key={slot.id}><strong>№ {slot.number}. {slot.title}</strong><p>{slot.summary}</p><code>{slot.id}</code></li>)}</ol>
    </div>;
  }
  const payload = preview.payload;
  return <div className="editor-mobile-preview"><h4>{String(payload.title)}</h4>
    <dl className="editor-ledger"><div><dt>Генератор</dt><dd><code>{String(payload.generator_id)}</code></dd></div>
      <div><dt>Версия</dt><dd><code>{String(payload.generator_version)}</code></dd></div>
      <div><dt>Позиция</dt><dd><code>{String(payload.slot_id)}</code></dd></div>
    </dl>
    <h5>Формулы модели</h5><p><RichText text={String(payload.formula_notes)} /></p>
    <h5>Ограничения</h5><ul>{strings(payload.constraints).map((constraint, index) => <li key={index}><RichText text={constraint} /></li>)}</ul>
    <p className="muted">Конкретный экземпляр доступен по seed после сохранения шаблона.</p>
  </div>;
}
