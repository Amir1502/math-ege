# Проверка безопасности исходников

## Продолжение: аккаунты, контрольные сессии и эксплуатация

**Дата:** 5 ноября 2026 года. Область — выборочная проверка завершения
утверждённого плана в приватном репозитории. Это не проникновение, не полный
построчный аудит и не разрешение публичного запуска. Исторический протокол
первой публикации сохранён ниже.

Карта границ: браузер и его очереди → API; opaque cookie → проверенный канонический
владелец → исходные пространства истории; редактор → проверенные data-only
ревизии; оператор → локальные PostgreSQL-инструменты и приватные резервные копии.
Входы: account/assessment/practice/editor HTTP-маршруты, ограниченный JSON,
CLI-аргументы и файлы оператора. Хранилища: PostgreSQL/SQLite, immutable snapshots,
IndexedDB, отдельные архивы и receipts. Авторизация проверяется в сервисах под
блокировками; клиентский owner-header — дополнительная защита от смены cookie,
а не заменитель авторизации.

### Измеренные сигналы

Viora Aegis 2.0.0, `scan --path backend/app` и `scan --path frontend/src`:

| Область | Файлы | Critical | High | Medium | Low |
| --- | ---: | ---: | ---: | ---: | ---: |
| Backend app | 80 | 1 | 3 | 19 | 1 |
| Frontend src | 124 | 0 | 1 | 4 | 0 |

Оба scan вернули **exit 1**; suppressions и ослабления правил не добавлялись.
Это исходные regex-сигналы, не число подтверждённых уязвимостей. Все пять
critical/high мест прочитаны и разобраны ниже. Локальные JSON-артефакты находятся
в игнорируемом `.viora/completion-{backend,frontend}.json`.

### Исправленный identity-race

Старый account-клиент закреплял владельца только для экспорта, а глобальная API
проверка исключала весь `/auth/`. Поэтому устаревший запрос с owner-header мог
дойти до logout/MFA для другой текущей cookie. Новая серверная регрессия
воспроизвела четыре отказа, включая успешные logout и enroll вместо 409.

`require_matching_identity` теперь исключает только bootstrap-маршруты
`/auth/config`, `/auth/request-link`, `/auth/complete` и существующие
`/identity`, `/guest`. Остальные scoped-запросы отклоняются до сервисной мутации
при несовпадении канонического владельца. Magic-link browser binding, проверка
сроков под блокировками, MFA и необязательность header для старых API-клиентов
сохранены. Scoped account-клиент и cancellation UI проверяются отдельно в
[`account-client.md`](account-client.md).

Свежая серверная проверка: Ruff exit 0; **92 passed in 36.67s** в
`test_account_identity`, `test_identity_integration`, `test_account_expiry`,
`test_account_deletion`, `test_account_integration`. Все базы — новые fixtures;
существующие данные не удалялись. Это подтверждённая функциональная race-регрессия;
полный доступ атакующего к origin браузера не становится безопасным от одного
owner-header.

### Разбор critical/high

```text
[CRITICAL signal] AI-001 — слово executor в документации rights
Where:   backend/app/operations/rights.py:4
Path:    docstring → regex; пути LLM output → executable sink нет
Impact:  исполнение модельного вывода этим местом не показано
Verdict: FALSE POSITIVE; Q1 no (это статический текст), Q2 no (не sink), Q3 нет исполнения
Fix:     не требуется; эксплуатационная актуальность текста проверяется отдельно
Verify:  прочитаны модуль и вызываемый read-only status/plan; исполняемого LLM API нет
Refs:    CWE-94 / Aegis AI-001

[HIGH signal] AI-004 — pg_dump назван agent tool
Where:   backend/app/operations/backup.py:194
Path:    оператор → проверенные source/head/private directory → fixed argv → pg_dump
Impact:  разрушение существующей базы этим read-only dump не показано
Verdict: FALSE POSITIVE; Q1 operator config, Q2 no destructive/LLM sink, Q3 только новый архив
Fix:     не требуется; сохранять allowlist программ, argv-массив и эксклюзивное создание файлов
Verify:  прочитаны create_backup и PostgresTools.transfer/command; shell=False по умолчанию
Refs:    CWE-250 / Aegis AI-004

[HIGH signal] AI-004 — pg_restore назван безусловно destructive
Where:   backend/app/operations/backup.py:260
Path:    оператор → checked manifest/checksum → validated new target → pg_restore
Impact:  восстановление поверх существующей пользовательской базы блокируется
Verdict: FALSE POSITIVE; Q2 no unsafe path: существующая/непустая цель отклоняется до restore
Fix:     не требуется; не добавлять --clean, --create или destructive recovery
Verify:  прочитаны restore_backup/restore_target; CREATE арбитрирует гонку, failures сохраняются
Refs:    CWE-250 / Aegis AI-004

[HIGH signal] PATH-001 — HTTP opener ошибочно принят за открытие файла
Where:   backend/app/operations/load_http.py:65
Path:    LoadConfig literal-loopback origin → fixed API routes/canonical IDs → urllib HTTP
Impact:  чтение произвольного локального файла этим HTTP call не показано
Verdict: FALSE POSITIVE; Q2 no filesystem sink; Q1 target только operator config
Fix:     не требуется; сохранять запрет redirects/proxies и явное разрешение remote HTTPS target
Verify:  прочитаны LoadConfig, VirtualUser._request и HttpTransport; ответы ограничены 2 MiB/timeout
Refs:    CWE-22 / Aegis PATH-001

[HIGH signal] XSS-002 — KaTeX HTML sink
Where:   frontend/src/components/math.tsx:24
Path:    content formula → KaTeX renderToString(trust=false, bounded) → HTML/MathML
Impact:  прямой путь raw input или exception text в HTML отсутствует
Verdict: FALSE POSITIVE; Q2 no bypass of KaTeX; error fallback — экранируемый React text
Fix:     не требуется по сигналу; не заменять markup исходной формулой/ошибкой
Verify:  прочитан renderer; свежая официальная документация Context7 подтверждает trust/bounds/error rules
Refs:    CWE-79 / https://katex.org/docs/security.html
```

Medium-сигналы `AUTH-005` относятся к lookup/повторной проверке SHA-256 дайджестов
opaque токенов, не к сравнению исходных паролей; SQLAlchemy использует параметры.
Исходный browser-state сравнивается через `secrets.compare_digest`. `DOS-001`
находит декораторы и клиентские route-строки, но не видит лимиты сервисов:
request-link — пять писем на email/час плюс общий limiter, complete — общий
limiter, MFA — пять попыток за пять минут и persisted replay tick. Config/logout
не проверяют угадываемый секрет. Low-сигнал очереди PostgreSQL опровергается
`Queue(maxsize=1024)`, ограниченной длиной строки и deadline.

### CI и supply chain

Для единственного workflow `.github/workflows/ci.yml` записаны факты:
trigger — push/main или обычный pull_request; actor — автор push/PR; permissions —
только contents:read; production secrets — не используются; untrusted — исходники
PR выполняются лишь в ephemeral runner; AI agent — отсутствует. Нет
pull_request_target, PR-head checkout с privileged token, OIDC или self-hosted
runner. PostgreSQL credentials случайно создаются, маскируются и не входят в
публикуемый evidence root. Privileged production цепочка не установлена.

Дополнительно: actor guard отсутствует для обычного unprivileged PR, что не
равно privileged-trigger доступу; agent tool grants отсутствуют, actions
закреплены полным SHA, `persist-credentials=false`. Workflow/internal ephemeral
credentials не передаются production-сервису. Финальный read-only CI-audit и
actionlint после reconciliation также завершились exit 0; **1 workflow,
0 findings/chains**. Логи в
`%LOCALAPPDATA%\Temp\opencode\completion-publish-abc814e2304c4ed3a7e532d4c139e474`.

Свежий `ci-audit`: **1 workflow, 0 findings, 0 chains**, exit 0. Actionlint,
source-hygiene и static infrastructure invariants также exit 0. Это не аудит
всего кода закреплённых actions. Offline `deps` для backend и frontend не нашёл
проверяемых supply-chain нарушений, но не обращался к advisory databases;
известные npm dev-уведомления и Python audit указаны в
[`dependencies.md`](dependencies.md).

### Подписанный Android-preview: ограничение API 23

Независимый bounded read-only разбор подтвердил **low integrity limitation**:
API 23 installer не аутентифицирует ordinary META-INF metadata contents по v1.
Q1: атакующий должен изменить APK до установки; Q2: first-party Java не читает
эти записи и runtime sink не найден; Q3: показана ограниченная подмена metadata,
не исполнения кода/перехвата данных. Проверка всех dependency consumers не
выполнена, поэтому APK-wide runtime exploit не объявляется ни подтверждённым,
ни полностью опровергнутым.

Принята только [точная preview-политика](android-signature-policy.md): raw API
23+ `-Werr` сохраняется **RED exit 1**; standard API 23+ exit 0 с ровно 20
literal warnings, API 24+ `-Werr` exit 0 без warnings. Все 48 исходных payload
entries и digests сохранены; signed alignment, compiled manifest и ожидаемый
сертификат проверены. Новый ключ, удаление metadata, пересборка, blanket warning
suppression и повторная подпись не выполнялись. Доставляемый SHA-256 и API 23
ограничение записаны в [Android-протоколе](android-preview.md). Проверка не
заменяет trusted distribution, device/OEM/TalkBack/live HTTPS acceptance.

### Не оценено в этой выборочной сверке

- Полный построчный аудит всех новых модулей, всего контента и зависимостей;
  отдельные subsystem reviews и tests не объявляются таким аудитом.
- Penetration testing, XSS fuzzing, временные каналы, TLS/cloud/IAM и OCI CVE.
- Android runtime, браузер/profile continuity и eventual HTTPS deployment;
  APK-проверка и её границы записываются отдельно.
- Независимо сохранённая production erasure mapping, юридическая политика
  резервных копий, SMTP/spool и данные несовершеннолетних.

## Историческая проверка первой публикации

**Дата:** 5 ноября 2026 года. **Область:** staged-реализация после `c163b34`, ветка `main`. **Метод:** Viora Aegis 2.0.0, проверка путей данных вручную, тесты API, локальные проверки KaTeX и lockfile. Публикация означает приватный GitHub, не запуск сервиса для учеников.

## Результат и границы

| Уровень | Сигналы сканера до разбора |
| --- | --- |
| Critical | 0 |
| High | 1 |
| Medium | 3 |
| Low | 0 |

Все четыре сигнала разобраны ниже. Подтверждённая уязвимость по этим сигналам не установлена; это не заключение об отсутствии уязвимостей во всём проекте. `scan --staged --fail-on high` возвращает **exit 1** из-за `XSS-002`; результат не скрыт подавлением правила или ослаблением проверок.

Рекомендация: исходники можно передать в согласованный приватный репозиторий. Публичный выпуск остаётся заблокирован непроверенным учебным контентом и оставшимися требованиями безопасности и эксплуатации. Известные dev-зависимости low/moderate остаются в `docs/dependencies.md`.

## Что проверено

- Входы: `backend/app/api.py`; изменяющие запросы: `backend/app/security.py` и строгие схемы `backend/app/schemas.py`.
- Доступ: `_guest_transaction`, `_owned`, `_help`, история и экспорт в `backend/app/services.py`. Закрытые маршруты передают cookie в сервис; выбор сессии ограничен одновременно её ID и ID гостя. История ограничена владельцем. Публичные маршруты — health, профиль, демонстрационные уроки и создание гостя.
- Хранилища: PostgreSQL/SQLite, IndexedDB и локальный журнал. Границы: браузер → API, гость → объект, контент → DOM, CI → GitHub.
- Наиболее крупные файлы: вручную прочитаны `services.py`, `schemas.py`, `test_api.py`, `test_security.py`, `test_content.py`, `frontend/tests/session.test.ts`, `profile.json`, `lessons.json`. Для `tasks.json` просмотрен представитель каждого из 15 семейств, все 65 ответов проверяются независимым от серверного checker вычислением. Для `package-lock.json` программно проверены все 511 записей: точная версия, HTTPS registry.npmjs.org и SHA-512 integrity, без ссылок на локальные пакеты.
- Дополнительно прочитаны место вставки KaTeX, Dockerfile, Compose, workflow и генератор PNG. Он читает только проектный SVG и сохраняет два заданных PNG; данные пользователя не отправляются.
- Шаблонная проверка исходников не обнаружила проверяемых форматов секретов. Проверки API покрывают чужую сессию, неверную cookie, фиксацию гостевого токена, запрет межсайтовой записи, предел тела и закрытые поля схем.

## Разбор сигналов

### [HIGH] XSS-002 — вставка результата KaTeX в DOM

Where: `frontend/src/components/math.tsx:24`, `MathFormula`.
Path: текст формулы → `katex.renderToString` → `dangerouslySetInnerHTML`.
Impact: сырая строка в таком месте могла бы выполнить код в origin приложения; прямого пути для неё здесь не найдено.
Verdict: **FALSE POSITIVE**, Q2: в sink поступает только результат KaTeX 0.19.1 с `trust: false`; при ошибке React выводит текст, не HTML.
Fix: изменение не требуется по этому сигналу; нельзя заменять результат KaTeX исходной строкой или текстом исключения.
Verify: локально проверены `href` с JavaScript URL, `includegraphics`, `htmlStyle`, текст с `script` и `img onerror`: четыре значения безопасно отрисованы, одно отклонено; обычная формула отрисована. Это пять контрольных примеров, не исчерпывающий XSS-аудит библиотеки.
Refs: CWE-79; [KaTeX security](https://katex.org/docs/security.html), [options](https://katex.org/docs/options.html), [handling errors](https://katex.org/docs/error.html).

- Q1: прямой записи формул учеником нет; серверный контент всё равно считается недоверенным.
- Q2: нет обхода преобразования — `markup` создаётся только `renderToString`; `trust: false` запрещает опасные команды, `strict: error`, `maxExpand: 100`, `maxSize: 10` ограничивают обработку.
- Q3: выполнения кода, создания ссылки или загрузки внешней картинки в контрольных примерах не обнаружено. Полный аудит KaTeX не выполнялся.

### [MEDIUM] AUTH-005 — сравнение дайджеста при поиске гостя

Where: `backend/app/services.py:102` и `:117`, `_guest_transaction` и `guest`.
Path: cookie → проверка формата → SHA-256 → параметризованный SQLAlchemy lookup.
Impact: сравнение исходного секрета с ранним выходом могло бы раскрывать его префикс; такого сравнения здесь нет.
Verdict: **FALSE POSITIVE**, Q2: `==` строит SQL-условие по дайджесту, а не сравнивает пароль в Python.
Fix: не заменять запрос вызовом `compare_digest`: это не SQL-предикат. Случайный токен создаётся через `secrets.token_urlsafe(32)`, исходное значение не хранится в базе.
Verify: `backend/tests/test_security.py` проверяет хранение только дайджеста, отказ для поддельной/неизвестной cookie и доступ только к своим объектам.
Refs: CWE-208; параметры SQLAlchemy и стандартные `secrets`/`hashlib`.

- Q1: да, клиент контролирует cookie, но не исходный случайный токен другого гостя.
- Q2: нет сравнения исходного секрета; после SHA-256 нельзя подбирать префикс токена по префиксу сравниваемого дайджеста.
- Q3: полезная утечка секрета или обход доступа не показаны; лабораторный анализ временных каналов базы не проводился.

### [MEDIUM] DEFAULT-109 — Uvicorn слушает интерфейсы контейнера

Where: `backend/Dockerfile:22`.
Path: статический CMD → интерфейс API-контейнера → nginx в Compose.
Impact: отдельная публикация API-порта может расширить доступ; поставляемый Compose не публикует этот порт.
Verdict: **FALSE POSITIVE** для поставляемой конфигурации, Q1/Q2: привязка задана разработчиком, внешнего проброса API нет; web опубликован только на `127.0.0.1:8080`.
Fix: привязка к `127.0.0.1` внутри API-контейнера сломает nginx. Не добавлять API `ports` без нового рассмотрения границы доступа.
Verify: `node scripts/verify-infra.mjs` и `docker compose config --quiet`; работа контейнеров подтверждается отдельно в `docs/verification.md`, не этим статическим выводом.
Refs: CWE-284; Compose service networking.

- Q1: нет, адрес слушателя — статическая конфигурация, не вход HTTP-запроса.
- Q2: путь из внешней сети к опубликованному API-порту отсутствует в Compose.
- Q3: доступность меняется при другом запуске контейнера; вывод не переносится на произвольный `docker run -p`.

## Ограничения инструментов

На Windows исходный scan упал при чтении UTF-8 diff как CP1251. Повтор с `python -X utf8` выполнил анализ. Ошибка запуска не считалась чистым результатом. `deps --format text` из печатного плана не поддерживается этой версией CLI; использован `deps --path backend` и `deps --path frontend`. Проверка только корня не обнаруживает manifest монорепозитория. Обе явно заданные области прошли offline-проверки, но они не обращаются к базам CVE; сетевые npm/pip-аудиты записаны отдельно.

## Не оценено

- Построчный аудит каждого файла вне перечисленных областей, всех записей контента, исходников 511 npm-пакетов и полного кода сторонних GitHub actions.
- Исчерпывающий XSS-fuzzing, временные каналы, проникновение, нагрузка и отказоустойчивость.
- Полная история git специализированным secret scanner: проверен текущий набор исходников, не выполнен gitleaks/trufflehog.
- CVE базовых OCI-образов и полный Linux-набор Python-пакетов; runtime Compose/PostgreSQL зависит от результата CI в протоколе проверки.
- Публичный домен, TLS, облачные разрешения, резервное восстановление и правовой режим данных несовершеннолетних.
