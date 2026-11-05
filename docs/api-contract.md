# Контракт первого этапа

База: `/api/v1`. JSON использует snake_case. Все ответы ошибок: `{"error":{"code":"...","message":"...","field":null}}`. Для числового поля `field` равно `answer`. Код 422 означает ошибку формата или схемы, 401 отсутствие гостевого сеанса, 404 отсутствие доступа к объекту, 409 конфликт, 503 выключенный демобанк.

Изменяющие запросы содержат `X-Requested-With: math-ege`. Создание сессии, отправка ответа и завершение дополнительно требуют `Idempotency-Key`, UUID. Браузер отправляет same-origin cookie; токен не доступен JavaScript. У `/guest` и запросов подсказок нет обязательного ключа.

## Контент

`GET /profile` возвращает:

```ts
type Skill = { id: string; title: string };
type Slot = {
  number: number; id: string; title: string; level: 'Б' | 'П';
  summary: string; skills: Skill[]; available_tasks: number; lesson_id: string;
};
type Profile = {
  id: string; year: number; title: string; status: 'draft'; revision: string;
  verified_at: string; verification_note: string; source_urls: string[];
  demo_mode: boolean; bank_size: number; slots: Slot[];
};
type Lesson = {
  id: string; title: string; slot: number; minutes: number; skill_ids: string[];
  sections: { heading: string; body: string; formula: string | null }[];
  example: { statement: string; steps: string[]; answer: string };
  takeaway: string;
};
type PublicTask = {
  id: string; revision: string; slot: number; topic: string; title: string;
  statement: string; formula: string | null;
  table: { headers: string[]; rows: string[][] } | null;
  skill_ids: string[]; family_id: string; estimated_seconds: number;
  review_status: 'demo'; hint_count: number;
};
```

`GET /lessons/{slot}` возвращает `Lesson`. В исходном JSON задачи дополнительно хранятся `answer: string`, `hints: string[3]`, `solution: string[]`, `source: {author, origin, rights, reviewed_by: null}`, `profile_id: string`, `difficulty: 1|2|3`, `rounding: null`. Публичный DTO этих полей не содержит. Файлы: `profile.json` (Profile без вычисляемых available_tasks/demo_mode/bank_size), `lessons.json` (Lesson[]), `tasks.json` (полные задачи[]).

## Сессии

`POST /guest` с `{}` возвращает `{id: string}` и устанавливает cookie. Повтор с действующим cookie сохраняет того же гостя.

```ts
type Attempt = {
  id: string; task_id: string; raw_answer: string; normalized_answer: string | null;
  correct: boolean; assisted: boolean; first_attempt: boolean; independent: boolean;
  skipped: boolean; active_seconds: number; created_at: string;
  expected_answer: string; solution: string[];
};
type Summary = {
  total: number; answered: number; independent_total: number; independent_correct: number;
  assisted: number; corrections: number; skipped: number; active_seconds: number;
};
type LearningSession = {
  id: string; profile_id: string; mode: 'practice'; status: 'active' | 'completed';
  created_at: string; completed_at: string | null; current_index: number;
  requested_length: number; notice: string | null; draft_revision: number;
  tasks: PublicTask[]; attempts: Attempt[];
  drafts: Record<string, { answer: string; active_seconds: number }>;
  help: Record<string, { hints: { level: number; text: string }[]; solution: { answer: string; steps: string[] } | null }>;
  summary: Summary;
};
```

- `POST /sessions`: `{slots: number[], length: 5|10|20, mode: 'practice'}` → `LearningSession`. Слоты уникальны и существуют в профиле. Уже выданные за 30 дней экземпляры исключаются. При частичной нехватке выдаётся меньшая серия с явным `notice`; при полном исчерпании 409 `bank_exhausted`.
- `GET /sessions/{id}` → `LearningSession`.
- `PUT /sessions/{id}/draft`: `{task_id, answer, active_seconds, expected_revision}` → `{draft_revision}`. Обновляет черновик этой задачи и текущий индекс. Ревизия меняется только при записи черновика. Несовпадение ревизии → 409 `draft_conflict`.
- `POST /sessions/{id}/attempts`: `{task_id, answer, active_seconds, skipped: boolean}` → `Attempt`. Формат дроби разрешён. При `skipped: true` ответ должен быть пустым, самостоятельная числовая попытка не создаётся. `active_seconds` означает суммарное активное время этой задачи, не приращение.
- `POST /sessions/{id}/hints`: `{task_id, level: 1|2|3}` → `{level, text}`. Перед первым ответом ставит признак помощи; после ответа не меняет исходную попытку.
- `POST /sessions/{id}/solution`: `{task_id}` → `{answer, steps}`. Имеет такое же правило помощи.
- `POST /sessions/{id}/finish`: `{}` → `LearningSession`. Неотправленные ответы не становятся математическими попытками. Повторное завершение не создаёт новый итог. Завершённую сессию нельзя менять.

## Прогресс

`GET /progress` требует гостевой cookie:

```ts
type Progress = {
  independent_total: number; independent_correct: number; assisted_total: number;
  corrections_total: number; skipped_total: number; active_session_id: string | null;
  slots: { number: number; attempts: number; correct: number;
    status: 'Нет данных' | 'Изучаю' | 'Закрепляю'; covered_skills: number; total_skills: number }[];
  recent_sessions: { id: string; status: 'active' | 'completed'; created_at: string; summary: Summary }[];
  mistakes: { task: PublicTask; attempt: Attempt }[];
};
```

`GET /export` возвращает `{version: '1', exported_at, profile_id, sessions: LearningSession[]}` без гостевого идентификатора, токена и хеша. `GET /health` по базовому пути `/api/v1/health` возвращает `{status:'ok'}` после проверки связи с БД.
