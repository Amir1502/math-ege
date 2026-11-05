# Протоколы технической проверки

## Расширение шести подсистем — 5 ноября 2026 года

Проверяется [утверждённое завершение](superpowers/specs/2026-11-05-completion-design.md)
в приватном репозитории. Это техническая проверка, а не полная предметная приёмка
`technical-spec.md` или разрешение публичной регистрации. Ниже сохранён
исторический протокол гостевого ядра; его числа не складываются с новыми.

### Завершённые общие проверки

| Проверка | Фактический результат |
| --- | --- |
| Backend: Ruff, `pip check`, затем весь pytest в новом `--basetemp`, без pytest cache | **20 411 passed, 2 skipped; 607,32 с; exit 0** в свежем delivery-gate. Ruff: `All checks passed!`; pip: `No broken requirements found`. |
| Полная серия практики из 20 задач: focused Chromium с реальным API | **1 passed, 25,0 с; exit 0**, сценарий 9,6 с. Двадцать исходных попыток/снимков и итог сохранены после reload; [границы доказательства](browser-integration.md#complete-twenty-task-practice-series). |
| Полный frontend: ESLint, Vitest, TypeScript/Vite build | **409 passed, 20 файлов, 17,08 с**; lint/unit/build — exit 0, без пропусков. Все 9 новых PWA-регрессий включены. |
| Все shared Chromium-сценарии, identity opt-in выключен | **26 passed, 4 намеренных identity skips, 0 failures/flaky; 108,515 с; exit 0**. Все три исходных PWA-сценария прошли без изменения их assertions. |
| Все четыре dedicated identity-сценария вместе | **4 passed, 0 skips/failures/flaky; 73,805 с; exit 0**, одна новая изолированная database/mailbox/dist/lock-среда. |
| Полный локальный unsigned Android strict-gate | **exit 0; 62 release-теста, 64 tooling-проверки / 6 PowerShell-файлов, 11 контрастных пар**; 0 lint errors/warnings, один wrapper-local `Hint`. [Протокол](android-preview.md). |
| Подписанный Android-preview, отдельный read-only gate | **exit 0 по точной preview-политике**: API 23+ standard exit 0 / ровно 20 разобранных META-INF warnings; API 24+ `-Werr` exit 0 / 0 warnings. Raw API 23+ `-Werr` остаётся **RED exit 1**. Signed alignment, manifest и все 48 исходных entries проверены. [Политика и ограничения](android-signature-policy.md). |

Команда из `backend/`:

```powershell
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m pip check
$run = Join-Path $env:LOCALAPPDATA ('Temp\opencode\completion-backend-final-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $run) { throw 'New isolated artifact path required' }
New-Item -ItemType Directory -Path $run | Out-Null
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp "$run/tests" --junitxml "$run/junit.xml"
```

Свежий JUnit сохранён вне Git в
`%LOCALAPPDATA%\Temp\opencode\completion-backend-final-998aea5c95c8480ca87f7d98cde8194d/junit.xml`.
SHA-256 — `5926f8ba17fa0fa8a42d528c9f49373d9daa47af62e39fb45fb9ff7f3df1ed6d`;
JUnit содержит 20 413 cases, 0 failures, 0 errors и 2 skips; его suite time —
606,813 с, вывод pytest — 607,32 с. `result.json` и список SHA-256 всех backend
исходников подтверждают неизменность файлов на протяжении команды.
Это whole local backend **после** адаптации rights/deletion, не прежние
20 400 тестов. Два пропуска — opt-in live PostgreSQL recovery в
`test_operations.py` и `test_postgres_recovery.py`; SQLite не подтверждает их.

Предыдущий одноимённый по области gate **20 411 passed, 2 skipped, 611,45 с**
остаётся отдельным историческим артефактом:
`backend-final-9fd803da01954358a80e76b1c3e2fe29.junit.xml`, SHA-256
`88a02f2946f6b3bc674a75b3fbbe6dd8c511bbfeab9931faa1fa23026c7dc794`.
Его результаты не суммируются со свежими; прежний файл и три защищённые
проверочные базы повторно подтверждены побайтно неизменными.

### Финальные локальные клиентские артефакты

Frontend и shared Chromium сохранены в новом
`%LOCALAPPDATA%\Temp\opencode\completion-final-verification-95dd0f8c856c40768203df33da81dfac`:

- `frontend/junit.xml`: **409 cases, 20 suites, 0 failures/errors/skips**;
  SHA-256 `bbc6ca6a39fd8d660a413c22aa7e8e5afaf09e47204502e42dbbb8361d142370`.
- `shared-chromium/report.json`: 30 сценариев, только четыре opt-in identity
  пропущены; SHA-256
  `2fd2658b8030f3aa25f8c5be37b79778599b79ca7581b87b86b61cd5e4d9bbbc`.
- `source-before.json`, результаты команд и `coordinator-consumption.json`:
  все **323 backend/frontend-файла** и их SHA-256 совпали при независимом чтении
  после завершения трёх gates. Это проверка финального локального кода, пока не
  свидетельство Linux CI на опубликованном commit SHA.
- Исходный `frontend/e2e/pwa.spec.ts` побайтно сохранён, SHA-256
  `bdee218963f254a77ff29b029c60137a2bddbccaaa48cafeea730a1169011264`.

Dedicated identity runtime:
`%LOCALAPPDATA%\Temp\opencode\completion-identity-final-c6008f8f701a4c9da64d8c3380e60e91`.
`report.json` SHA-256 —
`37445f815f81fa8942bde0fde967a2ff49dc6e2b9a5b724d15674ae0ceb08bf9`.
Четыре сценария выполнены **вместе**, не посредством сложения старых A/B/C runs.
Ни база, ни mailbox, ни dist, ни lock не переиспользованы. Automatic screenshots,
trace и video выключены; явные снимки и JSON-выгрузки остаются приватными вне Git.
Transient `ECONNREFUSED 127.0.0.1:8037` при startup readiness предшествовал здоровому
API и не является падением сценария. После завершения подтверждены 0 listeners
на 8000/5173/8037/5193 и отсутствие записанных identity runner/API процессов;
при потреблении доказательств никакие процессы не останавливались.

Первое потребление остановилось на проверке teardown: substring-фильтр command
line выбрал сам проверяющий PowerShell-процесс. Сохранён
`consumption-teardown-red.json`; после исключения собственного PID полный
`consume-final.ps1` завершился exit 0. Это ошибка consumption harness, а не RED
frontend/браузерных gates; исходники и runtime не изменялись.

### Подсистемные доказательства, хронология и ожидаемый CI

- [Identity/linking/export](identity-browser.md) сохраняет исторические A/B/C
  прогоны и отдельно новый общий **4/4 GREEN** координатора: два гостя и исходные
  ID/снимки, revoked credentials, same-owner stale-response cancellation,
  раздельные pending-очереди, четыре полные JSON-выгрузки со 104 аннотациями и
  раздельные закрытые/выпущенные итоги пробника. Остаточное offline
  identity-warning после reconnect не объявляется исправленным.
- Исторический whole frontend **400 passed / 18 файлов** до PWA и его JUnit
  `9d7ae2ff8c6d76e6f4892aef6fa24a0da3c359d7ada931f5a49e9778896a0298`
  не заменяются новым отчётом. Следовавший shared Chromium **RED: 24 passed,
  4 intentional identity skips, 2 original PWA failures**, SHA-256 отчёта
  `62723e7a4ed38caf0af17d639f9fe06639f5496691c922883f1c6f1c3b531666`,
  сохранён в `completion-browser-final-686d446f8e3e413db80bfe835061818c`.
  [Узкий PWA-handoff](pwa-regressions.md) подтвердил 9 новых регрессий в 61 scoped
  тесте и **3/3** исходных сценария дважды. Свежий общий GREEN приведён выше;
  исторический RED не переименован и числа разных срезов не суммируются.
- [Durable account-boundary proof](account-boundaries.md): **20 mounted +
  13 real IdentityManager**; portable focused run **33 passed** без
  `LOCALAPPDATA`/screenshots. Исторические 126/164 scoped gates остаются
  отдельными, а эти тесты включены в свежие 409.
- Linux CI на точном опубликованном SHA, расширенный Compose smoke и live
  PostgreSQL workload/recovery ещё не заявляются успешными. Локальные
  frontend/shared/identity gates завершены; CI-доказательства добавляются
  только после окончания соответствующих команд.
- Подготовка CI исправлена на уровне порядка зависимостей: Chromium устанавливается
  после `npm ci` и **до** `npm test`, поскольку mounted-компонентные тесты используют
  настоящий браузер. Новый порядок сначала воспроизведён как failing assertion в
  `scripts/verify-infra.mjs`, затем проверен exit 0 вместе с остальными invariants.
  `check-source.mjs` на прежнем срезе проверил 421 файл, exit 0. `.dockerignore`
  дополнительно исключает Android-дерево, APK и keystore-форматы; новые invariants
  наблюдались RED, затем GREEN. Свежие actionlint и read-only CI-audit: exit 0,
  один workflow, 0 findings/chains; внутренности actions и OCI CVE не проверены.
  Предыдущая сверка документации: 37 файлов, 0 несуществующих относительных
  ссылок. После финальной reconciliation повторены source hygiene (**429 файлов**),
  infrastructure invariants, actionlint и read-only CI-audit (**1 workflow,
  0 findings/chains**) — все exit 0. Финальный document checker: **39 документов,
  0 несуществующих относительных ссылок**, все **18 FR / 5 NFR / 27 AC** и
  неизменённое исходное ТЗ сохранены. Артефакты:
  `%LOCALAPPDATA%\Temp\opencode\completion-publish-abc814e2304c4ed3a7e532d4c139e474`.
  Это статические gates, не заявление об успешном выполнении Linux workflow.

Перед push raw-byte проверка Git обнаружила, что `core.autocrlf=true`
нормализовал CRLF только у `android/gradle/verification-metadata.xml` и
`android/gradlew.bat` в первом локальном implementation commit `f339d1a`.
Рабочие исходники, reviewed SHA-256 metadata/locks, unsigned/signed APK и
результаты gates не изменились. Публикация была остановлена; узкая
`.gitattributes` policy `-text` для этих двух путей сохраняет именно проверенные
байты в обычном follow-up commit, без amend/reset/force push. RED-карта
`git-byte-preservation-red.json` сохранена в delivery evidence root.
Для этих же двух CRLF-путей `whitespace` сохраняет проверки `blank-at-eol`,
`blank-at-eof`, `space-before-tab` и признаёт только `cr-at-eol` частью
терминатора. Иначе `diff --check` ошибочно считает каждый сохранённый CR
trailing whitespace; этот промежуточный RED также сохранён. Общие whitespace
проверки не выключены, `.gitattributes` не использует `-whitespace`.
- Unsigned Android gate и отдельный signed verifier завершены; исходный
  warning-strict **RED API 23+** сохранён. [Точная preview-политика](android-signature-policy.md)
  не устраняет API 23 META-INF integrity limitation. Signed APK: **90 065 байт**,
  SHA-256 `42199293d99b16b7003e7450e3f92a071b5971795c06c74c9ea340000f009dfd`;
  один ожидаемый preview сертификат, v1/v2/v3, actual `debuggable=false`, signed
  alignment exit 0; все 48 исходных ZIP entries сохранены, новый ключ/повторная
  подпись не выполнялись. Private prerelease, установка и действующий HTTPS
  endpoint пока не подтверждены. [Полная хронология](android-preview.md).

### Границы поставки

Кандидатный курс остаётся `demo`, профиль `draft`, независимые рецензенты —
`null`: 845 задач/99 уроков/26 runtime-шаблонов не заменяют ≥650 независимо
проверенных экземпляров и ручную проверку каждого шаблона. Программные пробелы
FR-03, FR-05/AC-06, положительного округления FR-12/AC-08 и событий/режима
аналитики NFR-05 сохраняются в [матрице приёмки](acceptance-status.md).
Авторитетное стирание после восстановления не реализовано:
`restore_replay_available=false`; production-promotion заблокирован.

Публичный HTTPS endpoint не назначен. APK-preview — только нативный запускатель
настраиваемого HTTPS-origin в браузере, не FastAPI/PostgreSQL внутри APK и не
автономное офлайн-приложение. Юридический режим, почта/TLS, реальные устройства,
screen reader, двухверсионное обновление PWA, production RPO/RTO и независимая
предметная приёмка не подтверждаются автоматическими локальными тестами.

## Исторический протокол первого этапа

Дата: **5 ноября 2026 года**. Проверяется утверждённое гостевое учебное ядро, не полная поставка `technical-spec.md`. Границы реализации: `docs/acceptance-status.md`; состояние банка: `docs/content-status.md`.

## Среда и воспроизведение

Локально: Windows, Python 3.13.14 в `backend/.venv`, Node.js 24.18.0, npm 12.0.1, Chromium/Playwright 1.64.1. Команды запуска находятся в README. Демобанк разрешён только явным `ALLOW_DEMO_CONTENT=true`.

API/E2E используют отдельные случайно названные временные SQLite-базы. Пользовательские базы не удаляются. Ручная браузерная проверка также изолирована; её серверы и браузеры остановлены после проверки. Production-сборка после проверки обновления service worker создана заново из исходников.

## Локальные автоматические результаты

| Проверка | Фактический результат |
| --- | --- |
| `.venv/Scripts/python.exe -m pytest -q` из `backend/` | **423 passed**, 22,81 с, exit 0 |
| `.venv/Scripts/python.exe -m ruff check .` | Все проверки прошли, exit 0 |
| `.venv/Scripts/python.exe -m pip check` | `No broken requirements found`, exit 0 |
| `npm run lint` из `frontend/` | ESLint, включая `tests/`, `e2e/`, `scripts/` и конфигурации, exit 0 |
| `npm run icons` | PNG 192×192 и 512×512 созданы из SVG; файлы включены в исходники, exit 0 |
| `npm test` | **41 passed**, 5 файлов Vitest, exit 0 |
| `npm run build` | TypeScript и production-сборка Vite прошли, exit 0; сгенерированы manifest и service worker |
| `npm run test:e2e` | **16 passed**, Chromium, 40,0 с, exit 0 |
| `node scripts/check-source.mjs` | Не найдены проверяемые форматы секретов, файлы баз и незакреплённые actions |
| `node scripts/verify-infra.mjs` | Статические ограничения Compose, Dockerfile, nginx и CI прошли |
| actionlint 1.7.12 | Workflow прошёл проверку, exit 0 |
| Standalone Docker Compose 5.7.0, `config --quiet` | Конфигурация с временным паролем разобрана, exit 0; это не запуск контейнеров |
| viora-aegis `ci-audit` | 1 workflow, 0 статических находок и 0 цепочек; не полный аудит сторонних actions |
| viora-aegis `scan --staged --fail-on high` | Exit 1: один high и три medium до разбора; пути данных и ложные срабатывания разобраны в `docs/security-review.md`, подавления не добавлялись |

E2E самостоятельно выполняет миграцию, запускает API, собирает клиент и поднимает `vite preview`. Service worker в обычном `vite dev` отключён, поэтому dev-сервер не служит доказательством офлайн-поведения.

Раздельно подтверждены exit 0 у actionlint и Compose. Отсутствие команды `docker` объясняет exit 1 раннего объединённого вызова, а не ошибку этих двух проверок.

## Поведение, проверенное через браузер

- Гостевой старт без регистрации; сохранение и восстановление того же экземпляра и черновика.
- Ошибка формата не создаёт математическую попытку. Сетевой сбой сохраняет ввод и не становится математической ошибкой.
- Неверный первый ответ, исправление, подсказка и решение перед другим ответом, пропуск, диалог завершения, итог, журнал ошибок и скачанный JSON.
- Контрольная серия из 5 задач: `independent_correct=0`, `independent_total=1`, `assisted=2`, `corrections=1`, `skipped=1`, `answered=2`. Исправление не переписывает первый результат. В выгрузке одна сессия и четыре попытки, без гостевых токенов и ключей идемпотентности.
- Escape закрывает диалог и возвращает фокус. Проверены ширины 320, 360, 390, 768, 1024 и 1440 CSS px, отсутствие горизонтального переполнения плана и axe WCAG A/AA на проверенных экранах.
- Поле ответа остаётся доступным на 320 CSS px при размере корневого текста 200%. Это не проверка всех устройств и не полный аудит WCAG.
- Реальный production-service-worker восстанавливает оболочку, открытый урок и черновик после офлайн-перезагрузки. В CacheStorage не обнаружено запросов `/api/`. Без сети серверная проверка ответов не заявляется.

### Исправленные браузерные регрессии

1. PWA-уведомление первого посещения перекрывало действие на телефоне. Оно перенесено в поток документа ниже основного содержимого. E2E проверяет расположение и успешный старт при видимом уведомлении.
2. На уроке № 6 axe воспроизводил `scrollable-region-focusable`. Блочная формула получила клавиатурный фокус и имя группы. Тест сначала упал на исходной версии, затем прошёл после исправления, включая прокрутку стрелкой вправо.
3. Во время ранней ручной проверки замена обслуживаемого `dist` вызвала 404 старого ленивого модуля и ошибку динамического импорта. После перезагрузки сессия и итог восстановились. Ограничение смены ресурсов не скрыто: правила локального обновления и требования к будущему выпуску описаны в `docs/deployment.md`.
4. Финальная проверка состава исходников обнаружила отсутствующие PNG, объявленные manifest. Новый браузерный тест воспроизвёл HTML fallback вместо `image/png`. Добавлены растровые версии существующего SVG и воспроизводимый генератор; тест проверяет MIME, декодирование изображения и размеры 192×192 и 512×512.

### Ожидание обновления PWA

Дополнительно выполнена отдельная проверка в Chromium с активным service-worker controller. Изменены только байты сгенерированного `sw.js` проверочным комментарием, без удаления или замены ресурсов приложения. Новая регистрация перешла в `waiting: installed`.

На активной задаче остались тот же URL, черновик `60` и неизменный `performance.timeOrigin`; сообщение объявило отложенное обновление, кнопка «Обновить» отсутствовала. После отправки ответа и завершения появилась кнопка обновления. Только явное нажатие сменило `timeOrigin`, активировало worker и восстановило страницу итога. В завершающем сценарии консоль не содержала ошибок. Это доказательство откладывания активации, не тест полноценного выпуска двух разных версий приложения.

До создания гостя запрос `/progress` может возвращать ожидаемый 401; интерфейс показывает честное пустое состояние. Такой ответ не является ошибкой математической проверки.

## Визуальная проверка

Подтверждающие изображения получены из production-preview после исправлений: план 1440×900 и 390×844, мобильная задача, отложенное обновление и итог после обновления. Основное действие доступно, PWA-уведомление его не перекрывает; сохранены пять мобильных пунктов навигации и явные подписи деморежима.

- `check.mjs src index.html`: 48 файлов, 0 ошибок и 0 предупреждений.
- `wig.mjs src index.html`: 48 файлов, pass.
- `contrast.mjs src/styles/tokens.css`: 13 измеренных пар, 0 провалов.
- `ru.mjs src index.html`: 0 ошибок, одно осознанное предупреждение об официальной аббревиатуре «ФИПИ».

Удалена декоративная внутренняя тень выбранного варианта; плавающее уведомление заменено обычным блоком. Статические инструменты не заменяют просмотр изображений. Общий `verify.mjs` не дал итоговый pass: переданный HTML был ошибочно принят за файл токенов, а URL для его встроенной съёмки не задавался. Поэтому компоненты проверки запущены отдельно с корректной областью, изображения получены через Playwright CLI.

Локальные артефакты в игнорируемом `output/playwright/`: `plan-desktop-final.png`, `plan-mobile-final.png`, `session-mobile-final.png`, `pwa-deferred-final.png`, `pwa-updated-summary-final.png`. Они не входят в git. Полный JSON прежней ручной серии сохранён отдельно как проверочный артефакт, не пользовательская база.

## Зависимости

Production-only npm-аудит: **0** найденных уязвимостей, exit 0. Полный npm-аудит: **15** затронутых dev-пакетов, 2 low и 13 moderate, exit 1. `pip-audit` установленного Python-окружения: известных уязвимостей не найдено, exit 0. Версии, три исходных уведомления и ограничения оценки: `docs/dependencies.md`. Полный аудит зависимостей не объявляется чистым.

## GitHub Actions и контейнеры

Репозиторий: https://github.com/Amir1502/math-ege, приватный. Реализация опубликована коммитом `b7c1863c9b635a9784ecfa8d90e3de183bc2f176`. Контрольный запуск [42034306795](https://github.com/Amir1502/math-ege/actions/runs/42034306795) завершён 5 ноября 2026 года: **completed / success**. `gh run watch --exit-status` завершился успешно; дополнительно прочитаны JSON состояния jobs и журналы выполненных шагов.

| Job | Результат | Проверенное выполнение |
| --- | --- | --- |
| [`tests`](https://github.com/Amir1502/math-ege/actions/runs/42034306795/job/127268332828) | success, 2 мин 43 с | Ubuntu 24.04: **423 pytest**, 9,07 с; Ruff, ESLint, **41 Vitest**, TypeScript/Vite production build, production-only npm audit 0; **16 Chromium E2E**, 40,5 с |
| [`containers`](https://github.com/Amir1502/math-ege/actions/runs/42034306795/job/127268332267) | success, 1 мин 58 с | Compose config, сборка обоих Dockerfile, запуск PostgreSQL/API/nginx, healthcheck всех трёх сервисов, `scripts/container-smoke.mjs`, остановка без команды удаления томов |

Docker CLI/Engine локально недоступен; runtime-подтверждение получено именно в Linux CI, а не из локального статического разбора. Журнал показывает создание нового тома `math-ege_postgres_data`, готовность сервисов и `PostgreSQL + API + nginx: smoke checks passed.` Команда запуска API выполняет `alembic upgrade head` до Uvicorn; smoke использует начальную схему PostgreSQL для реальных чтений и записей через nginx.

Контейнерный smoke проверил гостевой цикл, профиль на 13 позиций и банк из 65 задач, отсутствие эталона в условии, подсказку/решение, признак помощи, повтор создания/ответа/завершения, два конкурентных запроса с одним ключом, экспорт, защитные HTTP-заголовки и 404 для чужого гостя. Это отдельный набор, **не все 423 pytest на PostgreSQL**. Не проверены горячая замена API с новым IP, фактические ответы шлюза при искусственном отказе, восстановление резервной копии и нагрузка.

Браузерный [артефакт 13417307778](https://github.com/Amir1502/math-ege/actions/runs/42034306795/artifacts/13417307778) успешно загружен; срок хранения workflow — 7 дней. Локальная копия журнала: игнорируемый `output/playwright/github-actions-42034306795.log`.

В успешном запуске есть предупреждения: закреплённый `actions/upload-artifact` v4 объявляет Node.js 20, а runner принудительно использует Node.js 24; в его коде отмечены устаревшие `punycode` и `url.parse`. Шаг загрузки артефакта прошёл. Замена major-версии action требует отдельной проверки; предупреждения не объявляются устранёнными. npm также сообщает об устаревшем `glob`, уже учтённом в `docs/dependencies.md`.

## Не проверено и не входит в разрешение выпуска

- Независимая предметная рецензия 65 демозадач и 13 уроков; 650 проверенных задач и 26 генераторов не поставлены.
- Пробник, серверный дедлайн, аккаунты, объединение устройств, редактор, полноценное освоение и интервальное повторение.
- Реальные Android/iPhone, Safari/Firefox, экранный диктор, все сочетания масштабирования и ориентации.
- Многовкладочное обновление PWA, непрерывная смена клиентских ресурсов, откат выпуска.
- Нагрузка, LCP/CLS в полевых условиях, резервное восстановление PostgreSQL, RPO/RTO, мониторинг, TLS и публичная инфраструктура.
- Аудит базовых OCI-образов, полного кода сторонних actions и юридический режим данных несовершеннолетних.

Техническая сверка проектной структуры ФИПИ записана в `docs/source-verification.md`; она не заменяет методическую рецензию. Публичный запуск для учеников не выполнен и не разрешён этим протоколом.
