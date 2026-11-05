import { ErrorNotice, Loading } from './ui';
import { useSavedAnnotations } from '../extras/hooks';
import { TaskAnnotations } from '../extras/task-annotations';
import '../styles/extras.css';

export function WorksheetAnnotations({ sessionId, taskId, showCause }: {
  sessionId: string;
  taskId: string;
  showCause: boolean;
}) {
  const annotations = useSavedAnnotations();
  if (!annotations.owner) return <p className="microcopy">Подключитесь к серверу, чтобы загрузить и изменить свои отметки.</p>;
  if (annotations.error) return <ErrorNotice message={annotations.error} retry={annotations.retry} />;
  if (!annotations.ready) return <Loading label="Загружаем ваши отметки" />;
  if (annotations.data === null) return <ErrorNotice message="Не удалось подтвердить сохранённые отметки. Обновите доступ и повторите запрос." retry={annotations.retry} />;
  const values = annotations.data.find((item) => item.session_id === sessionId && item.task_id === taskId)
    ?? { favourite: false, manual: false, not_understood: false, cause: null };
  return <TaskAnnotations sessionId={sessionId} taskId={taskId} values={values} showCause={showCause} />;
}
