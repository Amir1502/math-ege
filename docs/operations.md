# Эксплуатация и проверка восстановления

Состояние на 5 ноября 2026 года. Команды находятся в `scripts/ops/`, реализация — в `backend/app/operations/`, примеры расписания — в `infra/backup/`.

**CI-gate реального PostgreSQL-восстановления и нагрузки подготовлен; его приёмка ожидает запуска на точном закоммиченном SHA.** Последняя локальная проверка нового gate, операций и обработчика дедлайнов: **107 passed, 2 skipped**. Оба пропуска — явно включаемые PostgreSQL-тесты. Linux/PostgreSQL, десятиминутная нагрузка и эксплуатационный RPO/RTO локально не подтверждены. Команды, артефакты и границы доказательств — в разделе 9.

Связанные документы: [развёртывание](deployment.md), [ТЗ](../technical-spec.md), [утверждённый план](superpowers/plans/2026-11-05-completion.md).

## 1. Режимы команд и подготовка

Запускать через существующее окружение проекта: `backend/.venv/bin/python` на Linux или `backend/.venv/Scripts/python.exe` на Windows. Установка пакетов для этих команд не требуется. Рабочая директория для примеров — корень проекта, если явно не указано `backend/`.

| Команда | Поведение по умолчанию | Явное выполнение |
| --- | --- | --- |
| `backup.py backup --expected-head REVISION` | Создаёт новую копию | `--dry-run` проверяет параметры без подключения к БД и создания файлов |
| `backup.py restore ...` | Читает и проверяет локальный архив; БД не открывает | `--confirm-restore` создаёт новую проверочную БД и сверяет восстановленные данные |
| `backup.py retention` | Только план 30-дневного хранения и контрольные суммы | `--apply --confirm-delete-scope SHA256` после отдельного подтверждения области удаления |
| `data_rights.py status` / `plan ...` | Только чтение БД и количества записей | CLI никогда не исполняет удаление; capability схемы не заменяет live admin/MFA |
| `load_scenario.py --target-route /api/v1` | Проверяет параметры, отправляет **0 HTTP-запросов** | `--confirm-load` сначала проверяет изоляцию, затем запускает сценарий |

CLI выводят JSON с фиксированными кодами ошибок. Код выхода `2` означает отказ или ошибку настройки/ввода-вывода. Для нагрузки `1` означает невыполнение наблюдаемых клиентских условий; `0` сам по себе не означает приёмку AC-25. План с нулём кандидатов или заблокированными архивами также требует чтения результата.

### Переменные подключения

| Переменная | Назначение |
| --- | --- |
| `OPS_SOURCE_DATABASE` | Обязательное явное имя исходной PostgreSQL-БД для backup/restore, включая dry-run |
| `OPS_BACKUP_DIR` | Абсолютный выделенный каталог для backup/retention; для restore используется `--bundle` |
| `OPS_PROTECTED_DATABASES` | Дополнительные запрещённые цели восстановления, через запятую **без пробелов** |
| `OPS_PG_CONTAINER` | Точное имя/ID контейнера с `psql`, `pg_dump`, `pg_restore`; без переменной используются локальные клиенты |
| `PGUSER` | Обязательная роль PostgreSQL, в том числе при dry-run backup/restore |
| `PGHOST`, `PGPORT` | Адрес подключения в среде, где выполняются PostgreSQL-клиенты |
| `PGPASSFILE` | Внешний файл паролей libpq; в Docker это путь **внутри контейнера** |
| `PGSSLMODE`, `PGSSLROOTCERT` | Настройки TLS для PostgreSQL-клиентов |
| `OPS_EXPECTED_HEAD` | Точная ревизия для systemd/cron; сам Python CLI получает её через `--expected-head` |
| `OPS_DATABASE_URL` | Отдельный обязательный URL для read-only команд прав на данные |

Клиенты backup/restore не передают ambient `PG*`-переопределения (`PGPASSWORD`, `PGSERVICE`, `PGSERVICEFILE`, `PGOPTIONS`, `PGHOSTADDR`, `PGSYSCONFDIR`): такие ключи удаляются из child environment, а не выставляются пустыми, потому что libpq считает пустое значение заданным и падает на пустом service file до TCP-соединения. БД задаётся явно. Пароль передаётся через заранее подготовленный `PGPASSFILE`, а не аргумент командной строки. Файл паролей на Linux должен иметь режим `0600`; права Windows ACL и UID контейнера настраивает оператор. Значения секретов и содержимое архива не помещать в протокол.

Имена БД ограничены `[a-z][a-z0-9_]{0,62}`. Для копий нужны обычная файловая система с поддержкой hard link, абсолютные пути без symlink/junction и доступ только оператору. Новые каталоги/файлы создаются с режимами `0700`/`0600` на POSIX; права уже существующих каталогов и Windows ACL проверяются при подготовке хранилища. Не размещать отчёты внутри каталога отдельного архива: retention ожидает там ровно два известных файла.

Текущая ревизия исходников — `0008_account_deletion_completion` (`alembic heads`). Перед копированием указать ревизию **фактически развёрнутой** БД. Алиасы `head`, `heads`, `base` для `--expected-head` запрещены; значение `REPLACE_WITH_DEPLOYED_REVISION` в примере окружения нужно заменить.

## 2. Копирование PostgreSQL

### Linux с PostgreSQL в Docker

На хосте уже должны быть окружение проекта, доступ оператора к Docker и подготовленный файл паролей в контейнере, если он нужен для выбранного подключения. Поддерживается PostgreSQL 13+, текущий Compose использует 18; версии клиентов нужно согласовать с сервером. Роль копирования должна читать все таблицы источника без пропуска строк из-за RLS. Архив пишется на хост, даже когда PostgreSQL-клиенты работают в контейнере.

```sh
cd /opt/math-ege
umask 077
set -C
export OPS_SOURCE_DATABASE=math_ege
export OPS_PROTECTED_DATABASES=math_ege
export OPS_BACKUP_DIR=/var/lib/math-ege-backups
export OPS_PG_CONTAINER=math-ege-db-1
export PGUSER=math_ege
export PGPASSFILE=/run/secrets/math-ege-backup.pgpass
expected_head=0008_account_deletion_completion

./backend/.venv/bin/python scripts/ops/backup.py backup \
  --expected-head "$expected_head" --dry-run
```

После проверки параметров создать копию:

```sh
./backend/.venv/bin/python scripts/ops/backup.py backup \
  --expected-head "$expected_head"
```

### PowerShell с локальными PostgreSQL-клиентами

Адрес `127.0.0.1:55432` ниже — пример отдельно подготовленного подключения. Основной `compose.yaml` порт PostgreSQL на хост не публикует.

```powershell
Set-Location D:\math_ege
$python = (Resolve-Path .\backend\.venv\Scripts\python.exe).Path
$env:OPS_SOURCE_DATABASE = 'math_ege'
$env:OPS_PROTECTED_DATABASES = 'math_ege'
$env:OPS_BACKUP_DIR = 'D:\math-ege-ops\backups'
$env:OPS_PG_CONTAINER = $null
$env:PGHOST = '127.0.0.1'
$env:PGPORT = '55432'
$env:PGUSER = 'math_ege'
$env:PGPASSFILE = 'C:\Users\user\AppData\Local\math-ege-ops\pgpass.conf'
$expectedHead = '0008_account_deletion_completion'

& $python .\scripts\ops\backup.py backup --expected-head $expectedHead --dry-run
```

После проверки выполнить ту же команду без `--dry-run`:

```powershell
& $python .\scripts\ops\backup.py backup --expected-head $expectedHead
```

Для Docker на Windows задать `OPS_PG_CONTAINER` и параметры libpq относительно контейнера. Python передаёт бинарный архив напрямую; PowerShell получает только JSON-результат.

### Как устроена копия

Каждый запуск резервирует новый каталог `math_ege_<UTC timestamp>_<32 hex UUID>`:

```text
OPS_BACKUP_DIR/
  math_ege_20261105T120000Z_<uuid>/
    math_ege_20261105T120000Z_<uuid>.dump
    manifest.json
```

1. Открывается `REPEATABLE READ READ ONLY` транзакция; проверяются имя БД, версия сервера и точная ревизия Alembic.
2. `pg_export_snapshot()` предоставляет один snapshot для инвентаризации и `pg_dump --format=custom --snapshot=...`. Экспортирующая транзакция остаётся открытой до завершения dump.
3. PostgreSQL хеширует **каждую полную строку каждой public-таблицы**. В Python поступают только отсортированные SHA-256 строк; manifest хранит количества и итоговые хеши таблиц. Сверка включает исходные ID, ответы, JSON-снимки, отдельные результаты пробника и редакции, если эти таблицы есть в источнике. Дополнительные пользовательские схемы и более 256 public-таблиц отклоняются.
4. Dump сначала пишется в `.dump.partial`, синхронизируется и проверяется. Финальное имя публикуется через `os.link()` без замещения, затем снимается только собственное временное имя. Manifest публикуется таким же способом **последним**; его финальное имя — признак завершённой копии.
5. `backup_created` содержит checksum архива и `restoration_verified=false`. Копия становится проверенной восстановлением только после отдельной процедуры ниже.

На Windows синхронизируются файлы; POSIX дополнительно синхронизирует каталоги. Сбой сохраняет каталог запуска и partial-файлы. Если процесс прервался между созданием hard link и удалением временного имени, такая незавершённая копия не проходит обычную проверку. Автоматическая очистка этих артефактов отсутствует.

Типовые отказы: `migration_head_mismatch` — сверить ревизию источника/архива; `postgres_client_unavailable` — проверить наличие клиента и выбранный режим; `postgres_client_failed` — ошибка дочернего процесса; `postgres_client_reported_diagnostics` — клиент что-то записал в stderr, даже при коде выхода 0. Содержимое stderr намеренно не публикуется: оно может включать строки COPY или реквизиты подключения. Разбирать причину через доступную оператору диагностику, сохраняя артефакты отказа. `archive_checksum_mismatch` и `restored_history_or_snapshot_mismatch` означают, что проверка целостности не пройдена.

Dump содержит приватные данные, хотя manifest и CLI не выводят строки пользователей. Копия одной БД не заменяет сохранение конфигурации ролей, внешних секретов, исходного пакета `backend/content/`, медиа, образов и соответствующей версии приложения/миграций. Эти материалы нужны для полного восстановления сервиса и хранятся отдельно по принятой политике доступа.

## 3. Восстановление только в новую БД

Требования: корректный manifest и checksum, точная ревизия из архива, тот же major PostgreSQL, роль с правом создать БД через служебную БД `postgres`. Имя цели должно быть `verify_restore_*` и отсутствовать на сервере. Исходная БД, `postgres`, `template0`, `template1`, `math_ege` и `OPS_PROTECTED_DATABASES` запрещены как цели.

Указать **конкретный** каталог завершённой копии вместо `<backup_id>`. Сначала проверить файл без подключения к серверу:

```sh
bundle="$OPS_BACKUP_DIR/<backup_id>"
target="verify_restore_$(./backend/.venv/bin/python -c 'from uuid import uuid4; print(uuid4().hex)')"
./backend/.venv/bin/python scripts/ops/backup.py restore \
  --bundle "$bundle" --target-database "$target" \
  --expected-head "$expected_head" --dry-run
```

Dry-run сообщает `database_contacted=false`, `target_absence_checked=false`: отсутствие БД ещё не проверено. Для реального восстановления:

```sh
./backend/.venv/bin/python scripts/ops/backup.py restore \
  --bundle "$bundle" --target-database "$target" \
  --expected-head "$expected_head" --confirm-restore
```

PowerShell:

```powershell
$bundle = Join-Path $env:OPS_BACKUP_DIR '<backup_id>'
$target = 'verify_restore_' + [guid]::NewGuid().ToString('N')
& $python .\scripts\ops\backup.py restore --bundle $bundle `
  --target-database $target --expected-head $expectedHead --dry-run
& $python .\scripts\ops\backup.py restore --bundle $bundle `
  --target-database $target --expected-head $expectedHead --confirm-restore
```

Исполнитель проверяет отсутствие цели, делает `CREATE DATABASE ... TEMPLATE template0`, проверяет пустоту и вызывает `pg_restore --exit-on-error --single-transaction --no-owner --no-privileges --no-tablespaces`. Флаги `--clean` и `--create` не используются. Затем сверяются Alembic revision, количества и хеши **всех** public-таблиц с экспортом исходного snapshot.

Успех — `status=restore_verified` и `all_row_and_snapshot_checksums_match=true`. При любой ошибке новая БД и файлы сохраняются для разбора; повторная попытка требует другого нового имени. Переключение приложения на восстановленную БД — отдельное действие координатора, с проверкой ролей, конфигурации, запуска и пользовательских сценариев.

### RPO 24 часа / RTO 4 часа

Для подтверждения NFR-04 и AC-26 протокол должен содержать:

- точку восстановления и возраст последней пригодной завершённой копии; наблюдение за ежедневным расписанием и обнаружением пропуска;
- параметры и объём исходной БД, версию PostgreSQL/клиентов, диски, CPU/RAM, размещение копии и версии приложения/контента;
- время от объявления восстановления до доступного проверенного сервиса, включая получение копии, подготовку окружения, проверку checksum, запуск и контрольные сценарии;
- результат сверки пользователей, попыток, профилей, редакций и неизменяемых снимков, а также применение ранее исполненных запросов удаления после восстановления.

`elapsed_seconds` CLI измеряет создание/восстановление/сверку БД после первоначальной проверки bundle. Это часть RTO. Ответ всегда оставляет `production_recovery_acceptance=false`. Суточный timer без наблюдения и успешного recovery drill не доказывает RPO/RTO.

## 4. Ежедневное расписание и 30-дневное хранение

### systemd / cron

Оператор размещает и адаптирует файлы, сохраняя существующие конфигурации:

| Исходный пример | Путь установки |
| --- | --- |
| `infra/backup/backup.env.example` | `/etc/math-ege/backup.env`, доступ только оператору |
| `infra/backup/math-ege-backup.service` | `/etc/systemd/system/math-ege-backup.service` |
| `infra/backup/math-ege-backup.timer` | `/etc/systemd/system/math-ege-backup.timer` |

Подготовить пользователя/группу `math-ege-ops`, его доступ к Docker, окружение `/opt/math-ege/backend/.venv` и каталог `/var/lib/math-ege-backups`. При смене путей согласованно изменить `WorkingDirectory`, `ExecStart`, `RequiresMountsFor`, `ReadWritePaths` и окружение. Service использует фиксированный путь Python; `OPS_APP_DIR` используется cron-обёрткой. Unit запускает только backup, с `UMask=0077` и пределом 3 часа.

```sh
sudo systemd-analyze verify /etc/systemd/system/math-ege-backup.service /etc/systemd/system/math-ege-backup.timer
sudo systemctl daemon-reload
sudo systemctl start math-ege-backup.service
sudo systemctl show math-ege-backup.service --property=Result --property=ExecMainStatus
sudo systemctl enable --now math-ege-backup.timer
systemctl list-timers --all math-ege-backup.timer
sudo journalctl --unit=math-ege-backup.service --since=today --no-pager
```

Timer запускается ежедневно в **02:00 UTC**, `AccuracySec=1min`; `Persistent=true` запускает пропущенное срабатывание после возвращения хоста. Результат запуска и свежесть manifest должны наблюдаться внешним мониторингом. Счётчик web-процесса не получает результат отдельного CLI автоматически.

Для хоста с cron использовать `infra/backup/cron.example` в crontab оператора и UTC как часовой пояс cron. `scripts/ops/daily_backup.sh` читает `/etc/math-ege/backup.env` либо `OPS_BACKUP_ENV_FILE`. Файл окружения должен быть доверенным: shell его исполняет. Выбирается один планировщик, чтобы расписания не дублировались. Linux/Docker-запуск этих примеров в данной среде не проверен.

### Retention: сначала точная область, затем подтверждение

```sh
./backend/.venv/bin/python scripts/ops/backup.py retention --dry-run
```

```powershell
& $python .\scripts\ops\backup.py retention --dry-run
```

План включает только корректные завершённые bundle возрастом **не менее 30 суток**. Проверяются оба файла и checksum; чужие имена сохраняются. Незавершённые/повреждённые bundle, ссылки, будущие даты и дополнительные файлы считаются заблокированными. `deletion_scope_sha256` связывает абсолютный корень, конкретные имена, размеры и checksum кандидатов/manifest. Если `blocked_bundle_count > 0`, применение отклоняется целиком.

Оператор проверяет `candidates`, объём, наличие пригодных копий и отдельно подтверждает **именно эту** область удаления. После такого подтверждения команда имеет вид:

```sh
./backend/.venv/bin/python scripts/ops/backup.py retention \
  --apply --confirm-delete-scope '<approved deletion_scope_sha256>'
```

```powershell
& $python .\scripts\ops\backup.py retention --apply `
  --confirm-delete-scope '<approved deletion_scope_sha256>'
```

CLI пересчитывает область перед выполнением; изменение состава или checksum требует нового плана и подтверждения. Исполнитель удаляет только два проверенных файла и их ставший пустым каталог, без рекурсивной очистки. Это не транзакция файловой системы: прерванное применение может оставить частично обработанный набор, который нужно разобрать по сохранённому плану.

Значение SHA-256 — техническая блокировка; оно не заменяет отдельное согласие пользователя агенту на необратимое удаление. В выполненных проверках `--apply` с действительным разрешением не запускался. Планировщик backup также не вызывает retention. Поэтому фактическое соблюдение максимальных 30 дней, включая внешние копии и заблокированные артефакты, требует ответственного оператора и принятой политики хранения; наличие dry-run этого требования не закрывает. Проверочные БД и артефакты данной работы сохраняются вне управляемого backup-каталога.

## 5. Изолированная нагрузка 500 пользователей / 30 RPS / 600 секунд

### Условия допуска

- Клиенту нужны `OPS_LOAD_TARGET` — явный origin с портом, **без завершающего `/`**, `--target-route /api/v1` и `--confirm-load`.
- По умолчанию разрешён только литерал loopback, например `http://127.0.0.1:8001`; имя `localhost` отклоняется. Удалённый стенд дополнительно требует `--allow-remote-target` и HTTPS.
- И клиент, и сервер получают одинаковый `OPS_VERIFICATION_NAMESPACE=verify_load_<32 lowercase hex>`; сервер запускается с `APP_ENV=verification`.
- Фактическое имя PostgreSQL-БД либо stem абсолютного SQLite-файла должно совпадать с namespace. На сервере проверяются `SELECT current_database()` / `PRAGMA database_list`, а не только строка URL.
- В БД должны быть нулевые количества `guests`, `learning_sessions`, `attempts`. Preflight `/api/v1/operations/load-target` проверяет именно эти три таблицы, окружение и имя. На обычном окружении или при несовпадении имени маршрут возвращает 404.
- `ALLOWED_ORIGINS` содержит точный `OPS_LOAD_TARGET`. Для HTTP-стенда cookie не Secure; для HTTPS — Secure. Каждый фактический повтор сценария получает новую изолированную БД. Открытие UI с гостевым стартом перед нагрузкой сделает БД непустой.

Рабочий Compose с `math_ege` не соответствует этим условиям. Для Linux/PostgreSQL заранее выделить проверочный экземпляр с доступными `psql`, `pg_dump`, `pg_restore`, явным host/port и ролью `CREATEDB`; для Docker сетевой доступ этого стенда настраивает оператор инфраструктуры.

### Linux: новая PostgreSQL-БД и API

Каталог `/var/lib/math-ege-verification` заранее подготовлен для оператора. Следующие команды выполнять в отдельном shell проверочного стенда; пароль находится во внешнем pgpass-файле. Любая ошибка создания БД или миграции останавливает процедуру.

```sh
set -eu
set -C
umask 077
cd /opt/math-ege/backend
unset PGPASSWORD PGSERVICE PGSERVICEFILE PGOPTIONS PGHOSTADDR PGDATABASE
export PGHOST=127.0.0.1 PGPORT=55432 PGUSER=math_ege_verify
export PGPASSFILE=/etc/math-ege/verification.pgpass
OPS_VERIFICATION_NAMESPACE="verify_load_$(./.venv/bin/python -c 'from uuid import uuid4; print(uuid4().hex)')"
export OPS_VERIFICATION_NAMESPACE
export OPS_LOAD_TARGET=http://127.0.0.1:8001
export APP_ENV=verification
export ALLOWED_ORIGINS="$OPS_LOAD_TARGET"
export ALLOW_DEMO_CONTENT=true COOKIE_SECURE=false
export DATABASE_URL="postgresql+psycopg://$PGUSER@$PGHOST:$PGPORT/$OPS_VERIFICATION_NAMESPACE"
export OPS_RUN_DIR="/var/lib/math-ege-verification/$OPS_VERIFICATION_NAMESPACE"
mkdir "$OPS_RUN_DIR"
printf '%s\n' "$OPS_VERIFICATION_NAMESPACE" > "$OPS_RUN_DIR/namespace.txt"
psql --no-psqlrc --no-password --set=ON_ERROR_STOP=1 --dbname=postgres \
  --command="CREATE DATABASE \"$OPS_VERIFICATION_NAMESPACE\" WITH TEMPLATE template0;"
./.venv/bin/python -m alembic upgrade head
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --no-access-log
```

Оставить API в первом терминале. Во втором задать `OPS_RUN_DIR` как **точный каталог этого запуска** вместо `<namespace>`:

```sh
set -eu
cd /opt/math-ege
set -C
umask 077
export OPS_RUN_DIR='/var/lib/math-ege-verification/<namespace>'
OPS_VERIFICATION_NAMESPACE="$(cat "$OPS_RUN_DIR/namespace.txt")"
export OPS_VERIFICATION_NAMESPACE
export OPS_LOAD_TARGET=http://127.0.0.1:8001
./backend/.venv/bin/python scripts/ops/load_scenario.py --target-route /api/v1 --dry-run
./backend/.venv/bin/python scripts/ops/load_scenario.py --target-route /api/v1 \
  --users 500 --rps 30 --seconds 600 --max-in-flight 30 --timeout-seconds 5 \
  --confirm-load > "$OPS_RUN_DIR/load-report.json"
```

### PowerShell: новая SQLite-БД для проверки протокола

Этот вариант воспроизводит API-поток на Windows; его скорость не является измерением PostgreSQL-инфраструктуры. Команды не используют стандартный `backend/math_ege.sqlite3`.

```powershell
Set-Location D:\math_ege\backend
$python = (Resolve-Path .\.venv\Scripts\python.exe).Path
$env:OPS_VERIFICATION_NAMESPACE = 'verify_load_' + [guid]::NewGuid().ToString('N')
$runDir = Join-Path 'C:\Users\user\AppData\Local\Temp\opencode' $env:OPS_VERIFICATION_NAMESPACE
New-Item -ItemType Directory -Path $runDir -ErrorAction Stop | Out-Null
$dbPath = Join-Path $runDir ($env:OPS_VERIFICATION_NAMESPACE + '.sqlite3')
if (Test-Path -LiteralPath $dbPath) { throw 'Verification database already exists' }
$env:DATABASE_URL = 'sqlite:///' + $dbPath.Replace('\', '/')
$env:APP_ENV = 'verification'
$env:OPS_LOAD_TARGET = 'http://127.0.0.1:8001'
$env:ALLOWED_ORIGINS = $env:OPS_LOAD_TARGET
$env:ALLOW_DEMO_CONTENT = 'true'
$env:COOKIE_SECURE = 'false'
$env:OPS_VERIFICATION_NAMESPACE | Out-File -LiteralPath (Join-Path $runDir 'namespace.txt') -Encoding ascii -NoClobber
& $python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Verification migration failed' }
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --no-access-log
```

Во втором PowerShell-терминале указать точный сохранённый `$runDir`:

```powershell
Set-Location D:\math_ege
$python = (Resolve-Path .\backend\.venv\Scripts\python.exe).Path
$runDir = 'C:\Users\user\AppData\Local\Temp\opencode\<namespace>'
$env:OPS_VERIFICATION_NAMESPACE = (Get-Content -LiteralPath (Join-Path $runDir 'namespace.txt') -Raw).Trim()
$env:OPS_LOAD_TARGET = 'http://127.0.0.1:8001'
& $python .\scripts\ops\load_scenario.py --target-route /api/v1 --dry-run
if ($LASTEXITCODE -ne 0) { throw 'Load configuration rejected' }
$reportPath = Join-Path $runDir 'load-report.json'
if (Test-Path -LiteralPath $reportPath) { throw 'Load report already exists' }
& $python .\scripts\ops\load_scenario.py --target-route /api/v1 `
  --users 500 --rps 30 --seconds 600 --max-in-flight 30 --timeout-seconds 5 `
  --confirm-load | Out-File -LiteralPath $reportPath -Encoding utf8 -NoClobber
$loadExit = $LASTEXITCODE
if ($loadExit -ne 0) { throw 'Load conditions not met; inspect the preserved JSON report' }
```

После проверки остановить API обычным `Ctrl+C` и сохранить БД, JSON, конфигурацию стенда и версии ПО. Следующий запуск начинает новый namespace, без очистки истории предыдущего.

### Что измеряет сценарий

План — **18 000 запросов за 600 секунд**, плюс один предварительный запрос проверки изоляции вне измеряемой нагрузки. 500 логических пользователей имеют отдельные cookie jar и собственные сессии; одновременно выполняется не более 30 HTTP-запросов и не более одного на пользователя. Параметры ограничены сверху: 500 пользователей, 30 RPS, 600 секунд, 30 in-flight, timeout 10 секунд; значения по умолчанию — `500/30/600/30/5`.

Пользователь проходит гостевой старт → профиль → создание practice-серии из пяти задач → чтение → черновик с revision → попытка → health → следующие задачи → завершение. Используются реальные cookie, `Origin`, `X-Requested-With: math-ege`, UUID-ключи идемпотентности и повтор того же тела при разрешённом retry. Ответы — синтетические целые строки с неизвестной правильностью; эталоны не извлекаются. Соединения HTTP не переиспользуются, системный proxy отключён, redirect не выполняется, размер ответа ограничен 2 MiB.

Open-loop планировщик пропускает опоздавшие/перегруженные такты и явно считает их, вместо догоняющего всплеска. `409 bank_exhausted` учитывается отдельно: пользователь переходит к чтению профиля/health, а сценарий не получает ложный успех от этих лёгких запросов. Для повторной проверки нужен свежий стенд с достаточным доступным банком.

| Поле отчёта | Как читать |
| --- | --- |
| `requests_dispatched`, `requests_finished`, `missed_schedule_slots` | Реально отправленные/завершившиеся наблюдения и пропуски расписания |
| `http_statuses_received`, `http_responses_completed` | Полученный статус отдельно от полностью прочитанного HTTP-ответа; оборванный 5xx остаётся серверной ошибкой |
| `achieved_rps_including_drain`, `elapsed_seconds_including_drain` | Фактическая скорость и время с ожиданием последних ответов |
| `operations`, `status_counts`, `outcome_counts` | p50/p95/max по операциям, статусы и ошибки протокола/транспорта |
| `server_error_rate` | Число полученных 5xx / число полученных HTTP-статусов; транспортные ошибки дополнительно видны в outcomes |
| `bank_exhaustion_responses`, `bank_exhausted_users` | Исчерпание банка отдельно от 5xx и полезного выполнения |
| `guest_users_created`, `users_with_completed_session`, `active_logical_users_per_minute` | Реальная активность и завершение хотя бы одной серии каждым пользователем |
| `execution_complete` | Все запланированные запросы отправлены и полностью получены, без пропусков, все гости созданы |
| `workload_complete` | Дополнительно каждый пользователь завершил серию и каждое наблюдение успешно |
| `full_control_scenario_completed` | Полный полезный сценарий именно `500/30/600`, все пользователи активны в каждой минуте |
| `observed_client_thresholds_met` | Полезный сценарий и клиентские p95: attempt ≤ 500 мс, прочие операции ≤ 800 мс; доля 5xx < 1% |

Нужны оба последних флага: короткий запуск может пройти клиентские пороги, а полный сценарий может завершиться с высокой задержкой. Критерий полезного выполнения здесь строже допустимой доли 5xx: ошибки/retry остаются в отчёте и не дают `workload_complete=true`. Все задержки включают сеть и обработку клиента. Для **AC-25/NFR-01** дополнительно нужен протокол инфраструктуры и серверные времена проверки ответа без сети пользователя; LCP/CLS и мобильные устройства проверяются отдельно. Поле `acceptance` остаётся `requires_infrastructure_protocol_and_server_side_timings`.

## 6. Диагностика и интеграция наблюдений

Публичный `GET /api/v1/health` проверяет БД и возвращает минимальное `{"status":"ok"}`. При недоступности БД используется общая ошибка 503 без диагностических данных. `OperationHealth.public_snapshot(database_ok=...)` также предоставляет только статус.

`GET /api/v1/operations/health` вызывает реальный `accounts.require_staff(request)`: нужны действующая сессия, роль `methodist`/`admin` и недавняя подтверждённая MFA. Выключенные аккаунты или недоступная MFA дают 503; отсутствие сессии — 401, недостаточная роль/MFA — 403. При отсутствии `OperationHealth` после успешной авторизации возвращается 503 `operations_unavailable`.

Контракт `from app.operations import OperationHealth`:

- `record_job(name, success, now)` принимает только фиксированное имя, настоящий `bool` и timezone-aware время в неубывающем порядке;
- `snapshot()` возвращает process-local uptime, количество успехов/ошибок, последние attempt/success/failure, последовательные ошибки и срок retry;
- job labels: `deadline_reconcile`, `backup`, `restore_validation`, `deletion_plan`;
- `record_event(name, success)` принимает event labels `answer_check`, `generator`, `attempt_save`, `draft_save`;
- backoff после ошибок: 5, 10, 20, 40, 80, 160, 300 секунд, далее максимум 300; успех сбрасывает серию и задержку, сохраняя историю последней ошибки;
- `retry_delay(name, now)` возвращает оставшееся ожидание; `record_job` сам работу не планирует.

Состояние начинается с `not_run` и сбрасывается при перезапуске процесса. При нескольких workers каждый имеет собственные счётчики; это не общая durable-метрика. Метки не должны содержать account/guest ID, email, URL/query, ответы, секреты или тексты исключений.

**Состояние интеграции при этой проверке:** `app/main.py` уже подключает router и `app.state.operation_health`; `app/background.py` записывает `deadline_reconcile`, учитывает backoff и завершает текущую работу перед остановкой. Это проверено `tests/test_background.py` вместе с операционными тестами.

Учебный сервис создаёт `OperationHealth(now=clock())`; main и deadline worker
используют тот же внедряемый clock. Checker и runtime generator записывают
фактические выполнения, не idempotent replay. `observe_save(name)` считает успех
attempt/draft только после принятого commit; отказ и откат не становятся успехом.
Action-savepoint сохраняет разрешённую запись ошибки, не частично выполненную
мутацию; истёкшая авторизация не сохраняется как новая idempotent-операция.
Регрессии — `test_operation_integration.py`, `test_background.py` и отдельные
assessment/practice gates.

Внешние backup/restore/rights jobs ещё нужно передавать во внешний мониторинг.
CLI не обновляет память работающего API. Наблюдать свежесть копий, ошибки и
дедлайны, HTTP-доступность и сохранение; долговременные метрики, их доступ и
оповещения требуют развёрнутой конфигурации.

Операционные счётчики без PII не заменяют учебную аналитику NFR-05 и её согласованный правовой режим.

## 7. Права на данные: read-only наблюдение и защищённое исполнение

`OPS_DATABASE_URL` задаётся отдельно и явно. Для PostgreSQL рекомендуется роль чтения и внешний `PGPASSFILE`; URL не выводится. PostgreSQL-запросы выполняются в `REPEATABLE READ READ ONLY` со statement timeout 30 секунд. SQLite требует существующий абсолютный обычный файл без query-параметров и ссылок, открывается с `mode=ro`, `autocommit=False`; все количества читаются из одного snapshot.

```sh
export OPS_DATABASE_URL='postgresql+psycopg://math_ege_ops_read@127.0.0.1:55432/math_ege'
./backend/.venv/bin/python scripts/ops/data_rights.py status --dry-run
./backend/.venv/bin/python scripts/ops/data_rights.py plan \
  --account-id '<exact account UUID>' --request-id '<exact request UUID>' --dry-run
```

```powershell
$env:OPS_DATABASE_URL = 'sqlite:///D:/math-ege-ops/verification/existing-rights.sqlite3'
& $python .\scripts\ops\data_rights.py status --dry-run
& $python .\scripts\ops\data_rights.py plan `
  --account-id '<exact account UUID>' --request-id '<exact request UUID>' --dry-run
```

`status` сообщает requested/overdue/due-soon, время наблюдения
`observed_at`, ближайший `earliest_pending_deadline_at`, detached completed
receipts и **сейчас сохраняемые** cancellations. Последнее не lifetime-счётчик:
отмена сохраняется до удаления аккаунта. Для отсутствующих legacy terminal
таблиц количество равно `null`, не выдуманному нулю. Пустая очередь не означает
наличия работающего планировщика: `dispatcher_status=external_configuration_not_observed`.
Внешний монитор должен фиксировать последний успешный scan, ошибки, свежесть и
overdue alerts; unattended dispatcher этой командой не запускается.

`plan` требует точные ненулевые канонические account/request UUID, проверяет их
связь и `requested`. Срок должен быть **точно requested_at + 30 дней**, как у
исполнителя; requested_at не может лежать в будущем. План и явное исполнение
разрешены до срока; `deadline_reached` показывает его наступление.

Вывод — количества `active_cloud_v1`, без email/токенов/ответов/переданных UUID:
корневой гость и все claimed origins, practice/history/idempotency/assessments,
evidence/policy/annotations, access/MFA/consent, очередь и private cancellations.
Magic-link selection совпадает с исполнителем: email, исходные origins,
`credential_account_id`, текущие и исторические bearer associations. Дайджесты
и email остаются SQL-выражениями, не частью отчёта.

`audit_disposition` отдельно считает связанные subject-строки, совпадения email
в operator и объединение затронутых строк; **rows_deleted=0**. `%`, `_` и `/`
в email экранируются на стороне SQL как буквальные символы. Исполнитель
отвязывает account FK, сохраняет псевдонимный subject и переписывает free-text
operator в одноразовый opaque alias без обратной карты; канонические operator
UUID сохраняются. Редакторское псевдонимное авторство не удаляется вместе с
учебными данными; это требует согласованной privacy-политики.

Capability проверяет фактические таблицы/колонки/nullability, PK/FK и terminal
check constraints `0008`, а не только имя Alembic head. Legacy/partial schema
возвращает `fulfillment_available=false` и
`fulfillment_blocker=durable_completion_schema_required`. На полной схеме:

```json
{
  "fulfillment_available": true,
  "fulfillment_blocker": null,
  "requires_live_administrator_and_recent_mfa": true,
  "restore_replay_available": false,
  "restore_replay_blocker": "independent_completion_scope_mapping_required",
  "guest_cleanup_enabled": false
}
```

Это capability кода/схемы, **не авторизация и не доказательство deployed accounts**.
`AccountService.deletion` уже подключён: пользователь может отменить точный
request ID, администратор с действующей сессией/recent MFA — явно исполнить его
с `confirm=true` или прочитать detached receipt. Никакой сохранённый principal
из CLI не обходит эти проверки. Executor блокирует auth barriers, все owner roots,
account/request/credential/audit строки, затем заново проверяет live admin/MFA,
точную область и срок. Scoped purge и receipt коммитятся **одной транзакцией**.
Cancellation переносит request в private terminal storage; retry относится к
тому же ID. Completed/canceled retry не исполняет новую заявку. Активная очередь
по-прежнему допускает только `requested`; лишние due/error/completed states в
ней не нужны. Проверка deletion выполнялась лишь на новых fixtures, не на
существующих пользовательских базах.

### Восстановление после исполненного удаления

Detached `0008` receipt содержит request UUID/время/scope, **не удалённые
account/origin UUID**. Копия может предшествовать и самой заявке. Поэтому receipt
сам по себе не восстанавливает область удаления и не разрешает replay по email
(email может принадлежать уже новому аккаунту).

До production restore promotion нужна независимо сохранённая access-controlled
карта точных immutable request/account/root/origin/link/audit UUID и lineage,
связанная с фактическим completion. Read-only capture был бы лишь prepared
snapshot: связывание, отмена и новая заявка могут сделать его устаревшим.
Authoritative integration должна сверить область под финальными существующими
locks, потребовать durable capture до purge, однозначно связать completion с
версией capture и повторно проверить live MFA после блокирующего IO. Файловая
публикация и SQL commit не атомарны; uncertain/canceled/stale/corrupt outcomes
блокируют доступ к восстановленным данным, а не автоматически разрешают purge.

Такой capture/replay здесь **не реализован**; `restore_replay_available=false`.
Не внедрён и автоматический purge восстановленного production. Отдельно
авторизованный replay должен выполняться сначала против новой isolated target
по исходным UUID, включая surviving guest histories без account row, после
snapshot validation и до доступности сервиса; полнота исторических link/audit
associations требует своего доказательства. NFR-03/AC-27, legal/backup/mail/spool
policy и эксплуатационная приёмка остаются открытыми в этих внешних границах.

Принятый запрос не равен исполненному удалению. Гостевая очистка выключена;
истечение срока доступа не удаляет историю.

## 8. Обновления и сохранение PWA-ресурсов

Операционная процедура релиза должна хранить хешированные JS/CSS/шрифты/медиа **как минимум двух предыдущих релизов вместе с текущим**, и дольше, если ими ещё пользуются открытые вкладки или нужен откат. Это отдельная политика от 30-дневного хранения приватных копий БД.

1. Публиковать новый release в отдельный каталог/образ и сохранять старые immutable asset URL доступными. Переключать entrypoint/manifest атомарно после загрузки всех новых ресурсов; наличие старого каталога само по себе не помогает, если его URL уже не обслуживается.
2. Применять совместимые additive-миграции. Откат приложения должен учитывать совместимость предыдущей версии со схемой; исходные попытки и снимки сохраняются.
3. Сохранять режим service worker `prompt`, `skipWaiting=false`, `clientsClaim=false`. Обновление активной тренировки откладывается до завершения/сохранения; принудительная перезагрузка и очистка cookie/IndexedDB не являются процедурой релиза.
4. Перед переключением проверить активную вкладку под SW и ещё не управляемую вкладку, динамический импорт старого chunk, несколько вкладок, потерю сети, сохранение/восстановление черновика и откат. Зафиксировать доступность старых asset URL и отсутствие потерь/дубликатов попыток.

Текущее ограничение описано в [deployment.md](deployment.md#обновление-клиента-и-pwa): простая замена `dist`/web-контейнера не обеспечивает удержание старых ресурсов. Автоматизированная система хранения нескольких релизов и её сквозная проверка остаются задачей инфраструктуры/клиента; эти инструкции не являются доказательством безопасного rollout.

## 9. Проверка, артефакты и оставшиеся границы

### CI-gate `postgres-operations`

`.github/workflows/ci.yml` содержит отдельный job на `ubuntu-24.04`, Python 3.13 и PostgreSQL 18. Образ совпадает с уже закреплённым в проекте: `postgres:18-alpine@sha256:10a5c69a83035ab5239f5620d708520e8b28f5aa1f2b20143e6024532edadfb5`. Нативные `psql`, `pg_dump`, `pg_restore` major 18 устанавливаются из PGDG; перед подключением репозитория проверяется fingerprint ключа `B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8`.

Оркестратор — `scripts/ops/verify_postgres.py`. Он использует существующие backup/restore и `load_scenario.py`, обнаруживает единственную актуальную голову Alembic и выполняет два этапа:

1. **Recovery.** Запускает оба настоящих opt-in PostgreSQL-теста, требует успешный JUnit без пропусков и оба итоговых restore-отчёта. Новая фикстура отражает реальную схему `0001_learning_core` и через ORM заполняет все пять исходных таблиц: `guests`, `learning_sessions`, `attempts`, `seen_tasks`, `idempotency_records`. После upgrade до обнаруженной головы сравниваются все исходные колонки, ID, история и замороженные снимки. Затем добавляются данные accounts/assessments/editor/learning, включая разные server/local результаты, редакции, аудит, MFA-storage, отмену и receipt удаления, options/instance-поля. Выполняются `pg_dump` и восстановление в новую БД; сравниваются полные строки и PostgreSQL-хеши **всех public-таблиц**. Receipt и остальные данные здесь синтетические: фикстура проверяет сохранность хранения, не исполняет удаление.
2. **Workload.** Создаёт другую новую PostgreSQL-БД, мигрирует её до той же головы и запускает один Uvicorn на `http://127.0.0.1:8001`. После health, проверки пустого namespace и соответствия профиля вызывает реальный load CLI с `--users 500 --rps 30 --seconds 600 --max-in-flight 30 --timeout-seconds 5 --confirm-load`. Требуются 18 000 полностью завершённых HTTP-запросов, все 500 пользователей в каждой минуте, завершённая серия у каждого, отсутствие пропусков/исчерпания банка/ошибок и клиентские пороги из раздела 5. Проверяются фактически прошедшие ≥ 600 секунд, 500 сохранённых гостей, 500 владельцев завершённых пятизадачных серий, минимум 2 500 попыток и 3 500 idempotency-записей.

Этапы имеют отдельные отчёты: отказ recovery не подавляет workload, а проблема контента не мешает уже выполненной recovery-проверке. Любой отказ делает общий результат неуспешным. Успешный процесс pytest без двух real-test результатов, dry-run, сокращённая длительность и одни только параметры `500/30/600` не проходят gate.

#### Источники, контент и изоляция

- `--expected-commit` должен точно совпадать с `git rev-parse HEAD`; рабочее дерево должно быть чистым до и после проверки. В CI используется `${{ github.sha }}`; для `pull_request` это SHA проверяемого merge checkout. `gate/run.json` фиксирует этот SHA, обнаруженную голову, SHA-256 файлов миграций, версии пакетов/Python, CPU/RAM и архитектуру. Несколько голов Alembic отклоняются.
- Контент явно выбирается через `--content-dir .../backend/content/course` и передаётся API как `CONTENT_DIR`. Нужны материализованные `profile.json`, `lessons.json`, `tasks.json` в проверяемой ревизии. Минимум — 650 выдаваемых задач, 50 на каждый из 13 слотов и пять семейств на слот. Хеши и покрытие записываются до нагрузки и повторно проверяются после неё. Последняя локальная инвентаризация: **845 задач, 99 уроков**. Профиль пока `draft`, поэтому только на проверочном стенде включено `ALLOW_DEMO_CONTENT=true`; независимая содержательная приёмка этим не заявляется.
- Подключение прямое: явные loopback `PGHOST`, `PGPORT`, `PGUSER` и приватный абсолютный `PGPASSFILE`; `OPS_PG_CONTAINER` отсутствует. Проверяется major 18 сервера и всех трёх клиентов. Пароль CI генерируется на один запуск и хранится вне дерева артефактов в каталоге `0700`, файлы — `0600`. Подключение API использует libpq-окружение без пароля в URL/argv. Посторонние PG/service, account, pytest и Uvicorn-переопределения очищаются.
- Имена recovery-источников — `verify_restore_source_<uuid>` и `verify_recovery_source_<uuid>`; цели — `verify_restore_<uuid>`, БД нагрузки — `verify_load_<uuid>`. Источники создают сами тесты/gate. Перед созданием проверяется отсутствие; `CREATE DATABASE ... TEMPLATE template0` служит вторым атомарным барьером. Использование Compose-БД `math_ege` как источника gate не предусмотрено.
- Каталог `--artifacts-dir` и каждый pytest basetemp должны отсутствовать. Повтор требует нового каталога/namespace. Успешное или неуспешное завершение сохраняет БД и копии; автоматическая очистка и destructive retention не вызываются.
- Readiness PostgreSQL ограничен 90 секундами, API — 60; recovery pytest — 480, load CLI — 720, миграция load-БД — 120. Шаг gate ограничен 28 минутами, job — 40; базовый `tests` job увеличен до 30 минут. Scoped Ruff выполняется из `backend/`: при явном `--config` этот cwd нужен для правильного определения first-party imports.

После нагрузки Uvicorn останавливается, затем сохраняется отдельная копия синтетической load-БД, в том числе при отказе клиентских порогов. У неё остаётся `restoration_verified=false`: recovery доказывают два отдельных теста. Workflow останавливает только контейнер с сохранённым собственным CID и оставляет volume. На hosted runner сохранённый volume не переживает утилизацию машины, поэтому долговременное CI-доказательство — загруженные dump/manifest/отчёты.

#### Артефакты и чтение результата

`actions/upload-artifact` выполняется с `if: always()` и фиксированным путём `$RUNNER_TEMP/postgres-operations-<run_id>-<run_attempt>/`. Имя артефакта — **`postgres-operations-<run_id>-<run_attempt>`**, срок хранения — **30 дней**. Для частично завершённого запуска присутствуют только уже полученные файлы:

| Путь внутри артефакта | Содержание |
| --- | --- |
| `provisioning.json`, `postgres-image.txt`, `postgres-stop.json` | Имена собственного контейнера/volume, digest образа, факт остановки |
| `gate/run.json`, `gate/postgres-versions.json` | Точный checkout/миграции, параметры машины и версии |
| `gate/summary.json`, `gate/recovery-stage.json`, `gate/workload-stage.json` | Общий и раздельные статусы, фиксированные коды отказов, время |
| `gate/recovery-process.json`, `gate/recovery.junit.xml` | Exit code/timeout и результаты обоих настоящих PostgreSQL-тестов |
| `gate/pytest-recovery/**/preserved-postgres-targets.json` | Имена новых source/target до их создания |
| `gate/pytest-recovery/**/populated-migration-before.json`, `populated-migration-after.json`, `populated-head-storage.json` | Колонки, количества и хеши ORM-фикстуры до/после миграции и на голове |
| `gate/pytest-recovery/**/backups/<backup_id>/` | Настоящие recovery `.dump` и `manifest.json` |
| `gate/pytest-recovery/**/full-row-inventory-before.json`, `full-row-inventory-after.json` | Сравнимые PostgreSQL-хеши всех public-таблиц |
| `gate/pytest-recovery/**/postgres-restore-evidence.json`, `full-postgres-restore-evidence.json` | Итоговые доказательства восстановления; появляются после успешных сравнений |
| `gate/load-target.json`, `gate/load-content.json`, `gate/load-readiness.json` | Условия нагрузки, namespace, покрытие/хеши контента и готовность API |
| `gate/load-migration-process.json`, `gate/load-process.json`, `gate/workload.json` | Миграция, фактическое время процесса и неизменённый JSON load CLI |
| `gate/load-durable-counts.json`, `gate/api-stop.json`, `gate/load-backup.json`, `gate/load-backups/<backup_id>/` | Durable-счётчики успешного сценария, остановка и сохранённая load-копия |

JSON-отчёты содержат метаданные/количества/хеши. Recovery JUnit очищается **до сериализации**: текст исключений, captured output и user properties убираются; отдельно обработаны collection и internal errors pytest. Raw stdout/stderr PostgreSQL, миграций и Uvicorn не публикуются. Dump содержит только созданные gate синтетические записи и не включает глобальные роли/пароль PostgreSQL. Файлы pgpass и server-password находятся вне загружаемого корня.

При разборе сначала сопоставить `gate/run.json.checked_out_commit` с SHA нужного CI-запуска, затем прочитать `summary.json`, оба stage-отчёта, JUnit, restore-хеши и workload. Наличие артефакта или успешного provisioning не означает успешный gate. При timeout/отказе сохраняются уже полученные материалы; повтор начинается с новых имён.

#### Запуск того же gate на подготовленном Linux-стенде

Нужны чистый checkout с материализованным course, существующий project dev-venv, PostgreSQL 18 с нативными клиентами 18, свободный порт API 8001, внешний pgpass и роль с `CREATEDB`. Каталог `/var/lib/math-ege-verification` заранее доступен оператору. Из корня проекта:

```sh
set -eu
umask 077
unset OPS_PG_CONTAINER
export PGHOST=127.0.0.1 PGPORT=55432 PGUSER=verify_admin
export PGPASSFILE=/etc/math-ege/verification.pgpass
run="/var/lib/math-ege-verification/gate-$(./backend/.venv/bin/python -c 'from uuid import uuid4; print(uuid4().hex)')"
test ! -e "$run"
expected_commit="$(git rev-parse --verify HEAD)"
./backend/.venv/bin/python scripts/ops/verify_postgres.py \
  --artifacts-dir "$run" --expected-commit "$expected_commit" \
  --content-dir "$PWD/backend/content/course"
```

Это выполняющая команда, без dry-run и без уменьшения нагрузки. Код `0` означает прохождение обоих этапов gate; `1` — отказ, смотреть сохранённый `summary.json`. `--help` не подключается к БД. На Windows оркестратор отказывает с `linux_project_venv_required`; переносимые локальные тесты ниже остаются доступными.

### Воспроизводимый локальный прогон

Каждый `--basetemp` должен быть **новым**: pytest может очистить уже существующий каталог. Родитель должен существовать. Не переиспользовать сохранённые пути, не включать очистку предыдущих проверочных БД/архивов.

```powershell
Set-Location D:\math_ege\backend
$env:OPS_RUN_POSTGRES_VERIFY = '0'
$env:PYTHONDONTWRITEBYTECODE = '1'
$run = Join-Path 'C:\Users\user\AppData\Local\Temp\opencode' ('ops-verification-' + [guid]::NewGuid().ToString('N'))
if ((Test-Path -LiteralPath $run) -or (Test-Path -LiteralPath "$run.junit.xml")) { throw 'Verification artifact path already exists' }
& .\.venv\Scripts\python.exe -m pytest tests/test_postgres_recovery.py tests/test_operations.py tests/test_background.py -q -p no:cacheprovider --basetemp "$run" --junitxml "$run.junit.xml"
if ($LASTEXITCODE -ne 0) { throw 'Operations verification failed; artifacts preserved' }
& .\.venv\Scripts\python.exe -m ruff check --config pyproject.toml tests/test_postgres_recovery.py ../scripts/ops/verify_postgres.py
if ($LASTEXITCODE -ne 0) { throw 'Scoped Ruff check failed' }
& .\.venv\Scripts\python.exe -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Installed dependency check failed' }
```

Linux, из `backend/`, с заранее подготовленным родительским каталогом:

```sh
set -eu
export PYTHONDONTWRITEBYTECODE=1
run="/var/lib/math-ege-verification/ops-$(./.venv/bin/python -c 'from uuid import uuid4; print(uuid4().hex)')"
test ! -e "$run"
test ! -e "$run.junit.xml"
OPS_RUN_POSTGRES_VERIFY=0 ./.venv/bin/python -m pytest \
  tests/test_postgres_recovery.py tests/test_operations.py tests/test_background.py \
  -q -p no:cacheprovider --basetemp "$run" --junitxml "$run.junit.xml"
./.venv/bin/python -m ruff check --config pyproject.toml \
  tests/test_postgres_recovery.py ../scripts/ops/verify_postgres.py
./.venv/bin/python -m pip check
```

### Только opt-in recovery без нагрузки

Нужны локальные клиенты и отдельный PostgreSQL-стенд с тем же прямым loopback/pgpass-подключением. Эти команды запускают оба recovery-теста и sanitizer JUnit; они не являются полным Linux-gate и не проверяют нагрузку или чистоту checkout.

Linux, из `backend/`:

```sh
set -eu
umask 077
unset OPS_PG_CONTAINER
export PGHOST=127.0.0.1 PGPORT=55432 PGUSER=verify_admin
export PGPASSFILE=/etc/math-ege/verification.pgpass
export PYTHONPATH="$PWD:$PWD/../scripts/ops"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1
run="/var/lib/math-ege-verification/pg-$(./.venv/bin/python -c 'from uuid import uuid4; print(uuid4().hex)')"
test ! -e "$run"
test ! -e "$run.junit.xml"
OPS_RUN_POSTGRES_VERIFY=1 ./.venv/bin/python -m pytest \
  'tests/test_operations.py::test_populated_initial_migration_preserves_ids_history_and_frozen_snapshots[postgresql]' \
  'tests/test_postgres_recovery.py::test_full_populated_migration_and_backup_restore[postgresql]' \
  -q --tb=no --show-capture=no -p no:cacheprovider -p verify_postgres \
  -o junit_logging=no --basetemp "$run" --junitxml "$run.junit.xml"
```

PowerShell, из `backend/`:

```powershell
$env:OPS_PG_CONTAINER = $null
$env:PGHOST = '127.0.0.1'
$env:PGPORT = '55432'
$env:PGUSER = 'verify_admin'
$env:PGPASSFILE = 'C:\Users\user\AppData\Local\math-ege-ops\verification.pgpass'
$env:PYTHONPATH = (Get-Location).Path + [IO.Path]::PathSeparator + (Resolve-Path ..\scripts\ops).Path
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$run = Join-Path 'C:\Users\user\AppData\Local\Temp\opencode' ('ops-postgres-' + [guid]::NewGuid().ToString('N'))
if ((Test-Path -LiteralPath $run) -or (Test-Path -LiteralPath "$run.junit.xml")) { throw 'Verification artifact path already exists' }
$env:OPS_RUN_POSTGRES_VERIFY = '1'
try {
    & .\.venv\Scripts\python.exe -m pytest `
      'tests/test_operations.py::test_populated_initial_migration_preserves_ids_history_and_frozen_snapshots[postgresql]' `
      'tests/test_postgres_recovery.py::test_full_populated_migration_and_backup_restore[postgresql]' `
      -q --tb=no --show-capture=no -p no:cacheprovider -p verify_postgres `
      -o junit_logging=no --basetemp "$run" --junitxml "$run.junit.xml"
    $postgresExit = $LASTEXITCODE
} finally {
    $env:OPS_RUN_POSTGRES_VERIFY = '0'
}
if ($postgresExit -ne 0) { throw 'PostgreSQL verification failed; artifacts preserved' }
```

Каждый тест создаёт собственную пару source/target с именами выше. В basetemp сохраняются `preserved-postgres-targets.json`, `backups/` и миграционные инвентаризации; при успешных сравнениях — `postgres-restore-evidence.json` либо `full-postgres-restore-evidence.json`. Здесь JUnit находится **рядом** с basetemp; в полном gate — внутри `gate/`. При прерывании материалы сохраняются, повтор использует новые имена.

### Что действительно выполнено

Платформа: Windows, Python **3.13.14**, `D:\math_ege\backend\.venv\Scripts\python.exe`, проверено `venv=True`.

| Проверка | Результат / граница |
| --- | --- |
| `pytest tests/test_postgres_recovery.py tests/test_operations.py tests/test_background.py -q -p no:cacheprovider` | **107 passed, 2 skipped, 17.69 s** после заполнения полей/таблиц `0008`; оба пропуска — real PostgreSQL |
| Новый файл `test_postgres_recovery.py`, до расширения фикстуры `0008` | 29 passed, 1 skipped, 9.83 s, включая отдельный internal-error sanitizer |
| `pytest tests/test_operations.py -q` | 75 passed, 1 skipped, 9.74 s; исходный scoped-прогон |
| Отдельный повтор `test_operations.py test_background.py` | 78 passed, 1 skipped, 11.50 s; затем повторно включён в объединённый прогон выше |
| Scoped Ruff нового test/runner из `backend/` | Успешно; тот же cwd задан в CI. Исходный lint `app/operations` также проходил ранее |
| `python -m pip check`, `verify_postgres.py --help` | Успешно через существующий project venv; локальной установки пакетов не было |
| Динамическая голова и course inventory | `0008_account_deletion_completion`; 845 задач, 99 уроков, ≥ 5 семейств и ≥ 50 задач в каждом слоте; хеши сохранены |
| Viora CI-audit | 1 workflow, 0 findings; статическая проверка, не Linux-выполнение |
| `node scripts/check-source.mjs`, `node scripts/verify-infra.mjs` | Успешно: 354 исходных файла; закреплённые actions, loopback/private DB и read-only CI-инварианты |
| Runbook | 10 PowerShell-блоков разобраны без ошибок, 4 относительные ссылки существуют, JSON-пример валиден; команды из документа при этой проверке не исполнялись |
| Actionlint | Позднее координатор выполнил закреплённый локальный actionlint: exit 0; Linux/POSIX shell-выполнение этим не проверено |
| Backup/load dry-run | 0 подключений к БД / 0 HTTP-запросов, файлы копии не создавались |
| Restore dry-run | Checksum синтетического bundle проверен; `database_contacted=false`, `target_absence_checked=false` |
| Retention dry-run | 0 кандидатов в выбранной проверочной папке; действительное удаление не выполнялось |
| Rights status | Чтение изолированной SQLite-фикстуры; тесты проверяют сохранность байтов и согласованный snapshot при конкурентной записи |
| HTTP transport | Настоящий локальный HTTP-сервер для cookie/CSRF/idempotency, redirect, обрывов и лимита ответа; полезный API-поток дополнительно проверен через TestClient |
| Миграция заполненной SQLite | Все пять исходных таблиц через ORM, исходные колонки/ID/история/снимки сохранены через `0008`; последующая фикстура содержит все public-таблицы |
| Реальные PostgreSQL dump/restore, Linux/Docker timer | **Не выполнялись:** `docker`, `pg_dump`, `pg_restore`, `psql` отсутствуют в этой среде |
| 500 пользователей / 30 RPS / 600 s против API | **Не выполнялось**; тест планировщика и dry-run не являются десятиминутным замером |

**Область CI-audit:** Viora и ручное чтение `.github/workflows/ci.yml`, включая checkout, provisioning, обработку ошибок и upload. Зафиксированы шесть фактов:

1. Trigger — `push` в `main` и `pull_request`.
2. Инициаторы — пользователи с правом push либо участники PR согласно доступу частного репозитория; отдельного привилегированного PR-trigger нет.
3. Token permissions — только `contents: read`, checkout с `persist-credentials: false`; write/OIDC scopes отсутствуют.
4. Repository secrets не используются; пароль PostgreSQL временный, маскируется и хранится вне артефактов.
5. PR-код исполняется на hosted runner; значения checkout SHA/run ID передаются через окружение или поля action, текст PR в shell не подставляется. Работа job не требует публичного репозитория.
6. AI-agent в workflow не вызывается. Подтверждённых цепочек утечки секретов или повышения привилегий в проверенной области не найдено.

**Не оценено этим аудитом:** фактическое исполнение GitHub Actions, Docker/PGDG provisioning, PostgreSQL-восстановление, нагрузка, инфраструктурный RPO/RTO и безопасность других подсистем приложения.

Сохранённые пути:

- Объединённый gate/operations/background прогон: `C:\Users\user\AppData\Local\Temp\opencode\pg-gate-integrated-01c699bb413b4d95ad0a199354069072`; JUnit — тот же путь с суффиксом `.junit.xml`. Внутри `test_full_populated_migration_0/` находятся SQLite `populated-migration-before.json`, `populated-migration-after.json`, `populated-head-storage.json`.
- Инвентаризация расширенного course и головы: `C:\Users\user\AppData\Local\Temp\opencode\pg-gate-content-cc76dbe3923d4013a04d61f5a9235a8c.json`.
- Финальный CI-audit: `C:\Users\user\AppData\Local\Temp\opencode\pg-gate-viora-checked-613af156b3c24bd79160c6ff99f6c64b.json`; более ранние отчёты также сохранены.
- Проверка PowerShell-блоков, ссылок и JSON обновлённого runbook: `C:\Users\user\AppData\Local\Temp\opencode\pg-gate-runbook-6025109cf2db45e895de975933dc3ba4.json`. Его SHA относится к тексту до добавления ссылок на финальные проверки; проверенные команды не менялись.
- Предыдущие проверки нового файла: `C:\Users\user\AppData\Local\Temp\opencode\pg-gate-final-f9045c2359b44c5f9d7d1db8f1d8b3d1` и `pg-gate-dev-f422f2002d034ef2a229d1208c79ee91` в том же родительском каталоге; рядом сохранены JUnit.
- Отдельный повтор операций/worker: `C:\Users\user\AppData\Local\Temp\opencode\pg-gate-operations-d28eab351d75486db3532dca496cb454` и соседний `.junit.xml`.
- Синтетическая регрессия internal-error JUnit: сохранённый отказ `C:\Users\user\AppData\Local\Temp\opencode\pg-gate-junit-regression-5ad2127ee4d84a6194bd3e656422859a`; после исправления — `pg-gate-junit-fixed-49744573d6ac45c9919b9c94bb2af638` в том же каталоге. Секрет в этом тесте — искусственный sentinel.
- Финальный прогон после новых shared app-подключений: `C:\Users\user\AppData\Local\Temp\opencode\ops-final-c9fa3d4927d54b64b0149c57e225e598`; JUnit — тот же путь с суффиксом `.junit.xml`.
- Предыдущий интеграционный прогон: `C:\Users\user\AppData\Local\Temp\opencode\ops-handoff-6290ecb50dde4df8998a00a9ad5b3283`; JUnit — тот же путь с суффиксом `.junit.xml`.
- Исходный успешный scoped-прогон: `C:\Users\user\AppData\Local\Temp\opencode\ops-verification-9de4637456924a8186e2c2db7001d92c`; JUnit — соседний `ops-verification-9de4637456924a8186e2c2db7001d92c.junit.xml`.
- Его restore dry-run использовал `test_backup_is_unique_snapshot0\owned-backups\math_ege_20261105T120000Z_825484ca5c0e421b9b490f9bf4405da4`. Это **синтетический** `_FakePostgres` архив с manifest revision `0005_editor`, а не PostgreSQL-копия текущей ревизии.
- Ранние артефакты сохранены в `C:\Users\user\AppData\Local\Temp\opencode\ops-tests-e4f4a03f5e894694a0d1bb5529c01d9a`.
- Неуспешный запуск с отсутствующим родителем вложенного basetemp сохранён в `C:\Users\user\AppData\Local\Temp\opencode\ops-verification-743dd2eede98419583b8a7002eee39fd\operations.junit.xml`; успешные результаты выше относятся к последующим новым каталогам.

### Передача координатору и приёмка

- Включить все четыре файла текущего gate и материализованный `backend/content/course/` в итоговый commit; package уже проходит локальный минимальный контракт. Убедиться, что CI проверяет именно нужный SHA и оба real PostgreSQL-теста включены, затем сохранить артефакт `postgres-operations-<run_id>-<run_attempt>`. Локальный dirty checkout не является доказательством этой ревизии; здесь commit/push и live CI не выполнялись.
- **AC-25 / NFR-01:** провести полный сценарий на зафиксированной PostgreSQL-инфраструктуре, сохранить JSON и серверные времена; отдельно проверить мобильную производительность.
- **AC-26 / NFR-04:** получить успешный PostgreSQL recovery-stage и отдельно эксплуатационное восстановление, проверить расписание/доставку копий/оповещения и полный RPO/RTO. Успех gate не измеряет возраст суточной копии или время восстановления доступного production-сервиса.
- **NFR-03 / AC-27:** новая `0008` уже предоставляет cancellation/receipt и detached-аудит. Их сохранность включена в фикстуру; приёмка транзакционного удаления, политики аудита/копий и post-restore replay относится к отдельной интеграции аккаунтов. Count-only operational plan остаётся read-only.
- **NFR-04 / NFR-05:** clock/event-контракт подключён; внешние monitoring/alerts и согласованный правовой режим учебной аналитики ещё требуют эксплуатационной конфигурации.
- **FR-17 / NFR-04:** внедрить сохранение нескольких релизов PWA-ресурсов и проверить активные вкладки, офлайн/черновики и откат.

Текущая поставка gate ограничена `.github/workflows/ci.yml`, `backend/tests/test_postgres_recovery.py`, `scripts/ops/verify_postgres.py` и проверочными разделами этого документа. Ранее подготовленные операционные инструменты переиспользуются. Итоговую интеграцию приложения, контента и матрицу приёмки ведёт координатор. Проверочные материалы сохранены.

### Источники по инструментам

При реализации и сверке использованы официальные документы, Context7 и установленный CLI. Отдельные запросы Context7 были недоступны; GitHub context availability и PGDG дополнительно сверены по прямым официальным страницам:

- [PostgreSQL 18: pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html), [pg_restore](https://www.postgresql.org/docs/18/app-pgrestore.html), [password file](https://www.postgresql.org/docs/18/libpq-pgpass.html).
- [Docker container exec](https://docs.docker.com/reference/cli/docker/container/exec/), [systemd.timer](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html).
- [SQLAlchemy 2: SQLite transactions](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html), [Alembic commands](https://alembic.sqlalchemy.org/en/latest/api/commands.html).
- [Python 3.13: sqlite3](https://docs.python.org/3.13/library/sqlite3.html), [os](https://docs.python.org/3.13/library/os.html), [urllib.request](https://docs.python.org/3.13/library/urllib.request.html); установленный `python -m uvicorn --help`.
- [PostgreSQL PGDG Ubuntu](https://www.postgresql.org/download/linux/ubuntu/), [GitHub Actions context availability](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#context-availability), [pytest hooks](https://docs.pytest.org/en/stable/reference/reference.html#hooks), [Ruff configuration](https://docs.astral.sh/ruff/configuration/).
