# Сторонние зависимости

Точные версии Python закреплены в `backend/requirements.txt` и `requirements-dev.txt`; клиентские версии и integrity-записи находятся в `frontend/package-lock.json`. Ниже перечислены основные зависимости и их роль. Этот список не подменяет тексты лицензий установленных пакетов и сканирование текущих уведомлений безопасности.

| Пакет | Назначение | Лицензия проекта |
| --- | --- | --- |
| FastAPI | API и OpenAPI | MIT |
| Pydantic | Проверка схем | MIT |
| SQLAlchemy | Параметризованная работа с базой | MIT |
| Alembic | Миграции | MIT |
| psycopg | PostgreSQL-драйвер | LGPL-3.0-or-later; бинарные сборки включают собственные уведомления |
| Uvicorn | ASGI-сервер | BSD-3-Clause |
| cryptography | Fernet-шифрование MFA-секрета внешним ключом | Apache-2.0 или BSD-3-Clause |
| PyOTP | Библиотечная TOTP-проверка MFA | MIT |
| React / React DOM | Клиент | MIT |
| Vite и React plugin | Сборка и разработка | MIT |
| vite-plugin-pwa / Workbox | Manifest и кэш статической оболочки | MIT |
| idb | IndexedDB | ISC |
| KaTeX | Формулы HTML + MathML | MIT |
| Lucide React | Иконки | ISC |
| Inter / Manrope | Кириллические шрифты | SIL Open Font License 1.1 |
| TypeScript | Статические типы клиента | Apache-2.0 |
| ESLint и плагины | Линт клиента | MIT |
| pytest | Серверные тесты | MIT |
| Ruff | Линт Python | MIT |
| Vitest / fake-indexeddb | Клиентские тесты и IndexedDB в тестовой среде | MIT / Apache-2.0 |
| Playwright | Браузерная проверка | Apache-2.0 |
| axe-core | Автоматическая проверка доступности | MPL-2.0 |

Android-preview использует закреплённые AndroidX Browser/Core, JUnit и Gradle/AGP;
версии, strict dependency verification и происхождение toolchain фиксируются в
[`android-preview.md`](android-preview.md). Ключ подписи, его пароль и APK не
входят в исходники. Эта таблица не является отдельным CVE-аудитом Android SDK.

API проверки ответа не использует языковую модель или платный внешний сервис. Google Fonts не вызывается из браузера: используемые шрифты поставляются с клиентом. Никакие рекламные или сторонние аналитические SDK не подключены.

Базовые контейнерные образы и GitHub Actions закреплены digest/полным commit SHA. Такая фиксация воспроизводит выбранный артефакт, но сама по себе не доказывает отсутствие уязвимостей. Обновления выполняются отдельным изменением с повторной проверкой.

## Процедура проверки перед поставкой

```sh
cd frontend
npm audit --omit=dev --audit-level=high
npm audit
```

Для Python сканируется установленный набор либо полностью закреплённый файл требований через `pip-audit` из отдельного инструментального окружения. Сканер не устанавливается глобально. Отчёт фиксирует дату, источник уведомлений, проверенные версии и недоступные данные.

Не следует выводить «уязвимостей нет» из отсутствия сканера или сетевого доступа. Фактические проверки и ограничения записываются в `docs/verification.md` и `docs/security.md`.

## Известные уведомления на 5 ноября 2026 года

`npm audit --omit=dev --audit-level=high`: 0 найденных уязвимостей, exit 0. Полный `npm audit`: **15 затронутых пакетов** с учётом цепочек зависимостей, 2 low и 13 moderate, без high/critical; exit 1. Это три исходных уведомления, а не 15 разных дефектов приложения.

| Пакет в lockfile | Уведомление | Цепочка |
| --- | --- | --- |
| `minimatch@10.2.6` | [GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249), moderate: усиление потребления ресурсов glob-шаблоном | ESLint, typescript-eslint; Workbox через glob |
| `glob@11.1.0` | [GHSA-3g3m-2fjr-6pw4](https://github.com/advisories/GHSA-3g3m-2fjr-6pw4), moderate: обход отмены обхода файловой системы | vite-plugin-pwa → workbox-build |
| `deepmerge@4.3.1` | [GHSA-gcqx-w48m-w2h4](https://github.com/advisories/GHSA-gcqx-w48m-w2h4), low: изменение прототипа возвращаемого объекта | workbox-build → @rollup/plugin-node-resolve |

Пути подтверждены `npm ls minimatch glob deepmerge --all`. Они относятся к сборке и линту; доступность этих функций через ответ ученика не установлена. Это не основание считать инструменты сборки безопасными: недоверенный PR может менять их вход. CI ограничен временем, без production-секретов и с токеном только для чтения.

Предлагаемые `npm audit` замены верхнеуровневых зависимостей меняют совместимость. `npm audit fix --force` и принудительные major-overrides не применялись. Устранение требует отдельного согласованного обновления цепочек, повторного линта, сборки и PWA/E2E. До этого полный аудит не считается чистым.

`pip-audit` установленного Windows-окружения backend, включая `pip==26.3`, завершился с `No known vulnerabilities found`. Это результат базы известных уведомлений на дату проверки, не аудит исходников библиотек или контейнерной ОС. Полный Linux-набор и базовые OCI-образы отдельным CVE-сканером не проверялись.
