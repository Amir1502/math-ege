# Android: предварительная версия

Android APK в этом проекте является небольшим нативным запускателем серверного приложения «ЕГЭ Профиль 2027», а не автономной копией тренажёра.

## Статус проверки — 5 ноября 2026

**Полный локальный unsigned strict-gate завершён с exit 0.** Итоговая проверка координатора выполнила **64 tooling-проверки** с разбором **6 PowerShell-файлов**, обычную strict-сборку с сохранёнными locks, **62 release unit tests**, `assembleRelease` с R8/resource shrinking, `lintRelease`, APK inspection и **11 resource-color/ripple контрастных проверок**. Ошибок и предупреждений lint — **0**.

Единственный `AndroidGradlePluginVersion` (предложение Gradle 9.8.2 при закреплённом 9.5.1) классифицирован как informational `Hint` только для `gradle/wrapper/gradle-wrapper.properties` через `android/gradle/wrapper/lint.xml`. Версия 9.5.1, `warningsAsErrors`, compatibility-детектор `IncompatibleAndroidGradlePluginVersion`, закреплённые версии, `verification-metadata.xml` и оба lockfile не изменены; lint baseline не добавлялся.

Прежний handoff исполнителя `blocked-lint` и две воспроизводимые unsigned-сборки до wrapper-local lint policy сохранены ниже как отдельная историческая RED-хронология. Unsigned APK остаётся побайтно прежним (**78 186 байт**). Подписанный APK (**90 065 байт**) независимо проверен без изменения payload или повторной подписи: v1/v2/v3, один ожидаемый сертификат, signed alignment exit 0 и фактический `debuggable=false`. Принята только [точная preview-политика API 23 META-INF](android-signature-policy.md): исходный `-Werr --min-sdk-version 23` остаётся **RED (exit 1)**; стандартная проверка API 23+ — exit 0 с ровно 20 разобранными предупреждениями, строгая API 24+ — exit 0 без предупреждений. Проверка на устройстве и живой HTTPS endpoint не подтверждены. [Private prerelease `v0.1.0-preview`](https://github.com/Amir1502/math-ege/releases/tag/v0.1.0-preview) опубликован по прямому указанию владельца; он не означает успешную PostgreSQL-нагрузку или автономность приложения. [Протокол публикации](verification.md#второй-exact-sha-прогон-workload-red-и-причина).

## Что получает пользователь

- При первом запуске адрес сервера не задан.
- Пользователь вводит HTTPS-origin, сохраняет его и видит точный выбранный адрес перед открытием браузера.
- Допустимы доменное имя, IDN в нормализованном ASCII-виде, канонический IPv4 или IPv6 и необязательный порт. Путь, кроме завершающего `/`, параметры запроса, фрагмент и встроенные учётные данные не сохраняются.
- Ссылка открывается в Custom Tabs браузера по умолчанию. Если он не поддерживает Custom Tabs, используется обычное окно того же браузера, без автоматического перехода в Chrome или другой профиль.
- Адрес можно изменить через отдельную доступную кнопку. Несохранённый ввод не передаётся в браузер и не сохраняется в состоянии Activity. После пересоздания Activity форма снова содержит только ранее проверенный адрес либо остаётся пустой.

Для работы нужны доступный сервер приложения и HTTPS-сертификат, которому доверяет браузер. Сервер, база данных, почтовая доставка и домен не поставляются внутри APK. Публичная публикация или развёртывание сервера не выполняются автоматически.

## Границы безопасности

В приложении нет WebView, JavaScript-моста, перехвата ссылок входа, нативного сетевого клиента или обработки скачиваний. Нативное приложение сохраняет только проверенный origin. Сеансы, cookies, service worker, экспорт и ссылки из писем остаются в браузере.

Ссылка из письма должна открываться в том же браузере и профиле, где был начат вход. Другой браузер, приватный профиль и табличная область `sessionStorage` могут нарушить привязку входа; это проверяется на устройстве после появления рабочего сервера. Custom Tabs не гарантирует возможности, доступные только отдельно установленной PWA.

Manifest запрещает cleartext и резервное копирование. Единственная экспортированная Activity является запускателем, не принимает web-ссылки и не читает входящие endpoint/token extras. Native INTERNET permission не требуется: сетью занимается браузер.

Браузер определяется через scheme-only HTTPS intent и публичный `ResolveInfo.filter` с `GET_RESOLVED_FILTER`. Принимается только общий HTTPS-фильтр без ограничений по host, path или scheme-specific part; отсутствующий фильтр или системный resolver приводит к видимой ошибке, а не к выбору произвольного приложения. Скрытые Android API и reflection не используются. Custom Tabs и обычный fallback закреплены за одним выбранным package; ephemeral browsing явно выключен. Реальное поведение конкретного браузера и его профилей всё равно требует проверки на устройстве.

## Инструменты и воспроизводимость

| Компонент | Версия |
|---|---|
| JDK | 17 |
| Gradle | 9.5.1 |
| Android Gradle Plugin | 9.3.3 |
| compileSdk / targetSdk | 37 |
| SDK package | `platforms;android-37.0` |
| Build Tools | 36.0.0 |
| minSdk | 23, Android 6.0 |
| AndroidX Browser | 1.10.0 |
| AndroidX Core | 1.13.0, фактическая версия в транзитивном графе Browser/Activity |
| AndroidX Startup / ProfileInstaller | 1.1.1 / 1.3.1, уже присутствующие runtime-зависимости Browser |
| Локальные тесты | JUnit 4.13.2 |

У проекта нет Kotlin-исходников, отдельного Kotlin plugin, Compose или NDK. AGP 9.3 имеет встроенную поддержку Kotlin и использует toolchain/stdlib 2.2.10; связанные метаданные также закреплены. AndroidX включает необходимые транзитивные библиотеки. Прямой Core pin совпадает с версией 1.13.0, выбранной транзитивным Activity 1.9.0, а не принудительно понижает её. Startup и ProfileInstaller тех же уже закреплённых версий объявлены напрямую, чтобы lint видел классы адресных manifest-removal markers. Data-only сравнение подтвердило неизменность runtime-графов и их хешей; добавилась только compile/API-видимость двух существующих AAR.

Для Windows обнаруженный SDK находится в `C:\Android\Sdk`; JDK 17 находится в `C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot`. Эти значения не записываются в `local.properties` или исходники. Другой компьютер должен задать собственные `JAVA_HOME` и `ANDROID_HOME`.

### Проверенная поставка Gradle

Официальный ZIP:

```text
https://services.gradle.org/distributions/gradle-9.5.1-bin.zip
SHA-256: bafc141b619ad6350fd975fc903156dd5c151998cc8b058e8c1044ab5f7b031f
```

Официальный SHA-256 `gradle-wrapper.jar`:

```text
497c8c2a7e5031f6aa847f88104aa80a93532ec32ee17bdb8d1d2f67a194a9c7
```

`android/scripts/bootstrap-gradle.ps1` создаёт новую директорию только под `%LOCALAPPDATA%\Temp\opencode`, сверяет опубликованный checksum с закреплённым, проверяет ZIP перед распаковкой/исполнением, генерирует официальный wrapper и проверяет его JAR. Глобальный пользовательский `.gradle` не используется. Файл `.gradle/android/FakeDependency.jar` не является зависимостью проекта и никогда не должен попадать в classpath.

SHA-256 опубликованных основных Maven-артефактов:

```text
com.android.tools.build:gradle:9.3.3
5b30e0ba8f3304f95529f1326668ef16497a736838c90a68815a4211ee65b02d

androidx.browser:browser:1.10.0
fb40d1ee5fd910c9d112200868a9534156a7a999abc28fbb3c6815a2e3ac5150
```

Зависимости загружаются только через Google Maven и Maven Central. Начальный набор SHA-256 получают в отдельном plain-Gradle проекте `tooling/dependency-bootstrap.gradle`, который разрешает артефакты как данные и **не применяет скачанный AGP**. Перед переносом метаданных отдельно сверяются приведённые выше опубликованные хеши AGP и Browser. Затем используются `gradle/verification-metadata.xml`, строгая проверка зависимостей и строгие lockfiles приложения и buildscript. Обновление этих файлов является отдельной проверяемой операцией; обычная сборка не должна применять `--dependency-verification off`, `lenient` или автоматически принимать новые хеши.

Data-only capture разрешает отдельно API/compile и runtime графы приложения и локальных тестов, а также AGP, lint и Windows AAPT2. Эти графы могут выбирать разные версии транзитивных библиотек; разрешать только runtime недостаточно для строгой Java-компиляции.

Транзитивные хеши фиксируют содержимое, полученное через официальные Maven-репозитории во время отдельного data-only capture. Это не независимая криптографическая аттестация каждого транзитивного пакета и не полный аудит CVE.

### Сборка

Перед сборкой установить JDK 17, официальный SDK package `platforms;android-37.0`, Build Tools 36.0.0 и Android command-line tools с `apkanalyzer`. Задать JDK/SDK; не включать секреты в параметры запуска или репозиторий.

```powershell
$env:JAVA_HOME = 'C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot'
$env:ANDROID_HOME = 'C:\Android\Sdk'
Set-Location 'D:\math_ege\android'

.\scripts\build-preview.ps1
```

`build-preview.ps1` создаёт свежую директорию под `%LOCALAPPDATA%\Temp\opencode`, вызывает проверенный bootstrap и использует только полученные Gradle executable/user home. Перед повторным исполнением все распакованные файлы Gradle сверяются с проверенным официальным ZIP. Маркер `.zip.ok` не считается доказательством. Project cache также находится внутри этой отдельной директории, а не в корневой `.gradle` рабочего проекта.

Скрипты требуют отсутствия дополнительных `GRADLE_OPTS`, `JAVA_OPTS`, `JAVA_TOOL_OPTIONS`, `_JAVA_OPTIONS`, `JDK_JAVA_OPTIONS` и `APKANALYZER_OPTS`: они могут подменять параметры исполнения или подключать Java agent. Значения этих переменных не печатаются в логах. Не допускаются user-home init scripts, лишние файлы в проверенной поставке Gradle, trust bypasses в verification metadata или изменение published primary pins.

Скрипты проверяются на Windows. Capture закрепляет Windows-classifier AAPT2; сборка на другой ОС требует отдельного проверяемого capture platform-specific артефактов, а не отключения verification.

Обычная сборка требует уже проверенных `verification-metadata.xml`, `buildscript-gradle.lockfile`, `app/gradle.lockfile` и не обновляет их. Начальная загрузка зависимостей требует интернета. После заполнения изолированного кэша можно повторить сборку с его `toolchain.json`:

```powershell
.\scripts\build-preview.ps1 -ToolchainState 'C:\путь\из\лога\toolchain.json' -Offline
```

Путь должен вести к проверенному bootstrap внутри `%LOCALAPPDATA%\Temp\opencode`. Это путь к локальному файлу, не endpoint сервера.

`.gitattributes` запрещает text/EOL-нормализацию только для
`android/gradle/verification-metadata.xml` и `android/gradlew.bat`, чтобы Git
сохранял точные reviewed CRLF bytes независимо от `core.autocrlf`. Это не
изменение toolchain, checksum, lock, build script или APK payload. Raw-byte
gate перед push отдельно проверяет совпадение всех committed source blobs с
рабочими исходниками; первый EOL mismatch сохранён как RED в delivery evidence.
На этих же двух путях whitespace-проверка сохраняет `blank-at-eol`,
`blank-at-eof`, `space-before-tab`, добавляя только `cr-at-eol`, чтобы CRLF
терминатор не считался лишним пробелом. Общее отключение `-whitespace`
не применяется.

### Первичный capture и обновление зависимостей

Эту процедуру используют только при первичной подготовке или после отдельного review изменения закреплённых версий/хешей. При первичной подготовке файл verification metadata ещё не существует:

```powershell
$root = "$env:LOCALAPPDATA\Temp\opencode\math-ege-android-$([guid]::NewGuid().ToString('N'))"
.\scripts\bootstrap-gradle.ps1 -ToolchainRoot $root
.\scripts\capture-dependencies.ps1 -ToolchainState "$root\toolchain.json"
.\scripts\build-preview.ps1 -ToolchainState "$root\toolchain.json" -WriteLocks
```

Если метаданные уже существуют, capture намеренно прекращается. Флаг `-AllowMetadataUpdate` допускается только для проверяемого обновления, не как обход ошибки сборки. Сверить diff XML и lockfiles, происхождение новых артефактов и опубликованные primary checksums. Новые зависимости, обнаруженные строгой сборкой, сначала добавляются в data-only bootstrap; скачанный plugin не исполняется с автоматически ослабленной проверкой.

Wrapper также включён в исходники с закреплённым `distributionSha256Sum`. При прямом использовании `gradlew.bat` сначала проверить SHA-256 его JAR и обязательно задать **новый** `GRADLE_USER_HOME`; не использовать существующий глобальный кэш. Рекомендуемый и проверяемый путь — скрипт выше.

Результат: `android/app/build/outputs/apk/release/app-release-unsigned.apk`. Он не подписан и пока не устанавливается на обычное устройство.

### Локальная проверка результата

Скрипт сборки запускает `:app:testReleaseUnitTest`, `:app:assembleRelease`, `:app:lintRelease` с `--dependency-verification strict`. Release host tests явно включены через AGP 9.3 `HostTestBuilder`, без устаревшего `enableUnitTest`. Release включает R8/resource shrinking, `debuggable=false`, lint warnings-as-errors и не имеет signing configuration.

Перед Gradle gate `test-tooling.ps1` проверяет PowerShell syntax и fail-closed поведение при отключении metadata verification, trust bypass, отсутствующем/неправильном checksum, изменённом primary pin, запрещённых JVM/analyzer env-переменных, ослаблении lint-политики и отсутствующем native executable. Отдельные regression checks принимают только символьное `signature`, десятичное или шестнадцатеричное представление, приводящееся ровно к числовому значению `2`; неверные строки, `normal`/`dangerous`, `signatureOrSystem`, дополнительные flags и дубликаты объявления/использования отклоняются. Сначала воспроизведён RED для допустимого десятичного `"2"`, затем получены **63 passed**, после добавления проверки wrapper-local lint policy — **64 passed / 6 файлов PowerShell**. Fixtures создаются только в новой локальной temp-директории; они не исполняют plugins и не используют сеть.

После Gradle gate `validate-preview.ps1` проверяет уже собранный APK через `apkanalyzer`, `apksigner` и `zipalign`, а также читает JUnit/lint XML. Проверяются application ID, min/target SDK, отсутствие INTERNET/storage permission, запрет backup/cleartext, единственная экспортированная launcher Activity без web intent-filter, отсутствие signing block и JNI, выравнивание, доступный label и отсутствие сохраняемого draft. Проверка цветов использует фактические Android resource values и пороги 4,5:1 для текста / 3:1 для границы и фокуса. Проверяется также максимальная объявленная ripple opacity в active/release состояниях, чтобы нажатие не снижало контраст текста.

AndroidX Core может добавлять собственное `ru.mathege.preview.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION`; оно допускается только на уровне `signature` (в decoded manifest `apkanalyzer` это точное значение `0x2`, а в fixture-проверках — только `signature`, decimal или hex, равные `2`) и не даёт доступа к сети, хранилищу или пользовательским данным. Некорректные строки, дополнительные flags и дубликаты не принимаются.

Неиспользуемые транзитивные `androidx.startup.InitializationProvider` и `androidx.profileinstaller.ProfileInstallReceiver` исключены через адресные `tools:node="remove"` с `android:exported="false"`: этому запускателю не нужны автоматическая запись profiling-данных и экспортированный диагностический receiver. Классы этих markers доступны lint через прямые pins уже существующих runtime-зависимостей. Зависимости Browser не удаляются из classpath; APK validation отдельно требует отсутствия всех provider/receiver. `removeAll` не используется: merger запрещает ему дополнительные Android-атрибуты, а без явного `exported=false` lint ошибочно считает сам marker экспортированным provider.

Проверку можно повторить отдельно:

```powershell
.\scripts\validate-preview.ps1
```

После успешного полного unsigned gate создаётся `android/app/build/reports/android-preview/validation.json` и его внешняя копия в директории доказательств ниже. Единственная запись в `lint-results-release.xml` — wrapper-local `AndroidGradlePluginVersion` со `severity="Hint"`; ошибок и предупреждений `0`. Рядом сохраняются decoded manifest, вывод `apksigner` для unsigned APK и проверка alignment. Полный Gradle log находится в изолированном toolchain root; путь печатается при сборке. Ожидаемый ненулевой код `apksigner` на неподписанном APK подтверждает именно unsigned артефакт, а не проверку подписи.

### Артефакт и сохранённые доказательства

Unsigned APK: `android/app/build/outputs/apk/release/app-release-unsigned.apk`, **78 186 байт**. Application ID `ru.mathege.preview`, versionCode `1`, versionName `0.1.0-preview`.

```text
APK SHA-256:
df2b901b34001a73963f03eddf779a95a070c11fba84dce8e42beeeab2c69204

gradle/verification-metadata.xml SHA-256:
f35c5ebe0d3f9fadb0fb809fd15c96f6fe855390c67895355a4571f2e27c82f6

buildscript-gradle.lockfile SHA-256:
1fb2b2019f543f3295820733f8e61463cdaa1de19f0af11646ddc6e5a9124deb

app/gradle.lockfile SHA-256:
e52d4df0393398a39a17620d6d9124ffb89d8d7f798d1f2304f87bf85e0a84cf
```

### Итоговый локальный unsigned gate координатора

Внешние доказательства сохранены в
`%LOCALAPPDATA%\Temp\opencode\completion-android-final-3a297d1b1da643169549564efcfcc02a`:

- `full-gate-result.json`, `ordinary-strict-full-build.log`: **exit 0**, 58,86 с,
  62 release-теста, 64 tooling-проверки, 11 контрастных пар, неизменённые исходники,
  metadata и оба lockfile.
- `lint-final.xml`: ровно один `<issue id="AndroidGradlePluginVersion" severity="Hint" ...>`
  на `android/gradle/wrapper/gradle-wrapper.properties`; 0 ошибок и 0 предупреждений.
- `unsigned-validation.json`, `tooling-final.json`, `junit-final/`: `Signed=false`,
  `Debuggable=false`, 62 тестовых случая без failures/errors/skips.
- `coordinator-consumption.json` и `consumption-harness-diagnosis.json`:
  потребление артефактов подтвердило неизменность всех Android-файлов; отдельно
  записано, что ранняя обёртка `@(Get-Content ... | ConvertFrom-Json)` в
  PowerShell 5.1 создавала вложенный массив, а не изменение исходников.

### Исторические доказательства исполнителя до wrapper-local lint policy

До добавления `android/gradle/wrapper/lint.xml` две полные обычные strict-сборки с разными `GRADLE_USER_HOME` выполнили по 51 задаче и дали побайтно тот же APK. Каждая прошла assemble/62 release-теста и завершилась единственным `AndroidGradlePluginVersion`. Locks были получены отдельной успешной strict capture-операцией с release/test/lint-analysis задачами, потому что Gradle не записывает lock state после неудачного build; capture не является полным release gate. Вторая сборка не применяла `-WriteLocks` или metadata regeneration; оба lockfile, metadata и тогдашняя wrapper policy остались прежними. Data-only inventories обоих кэшей совпали по всем 276 записям. Это сохранённая историческая проверка воспроизводимости и RED-состояния на одном Windows-компьютере, не независимая проверка на другом хосте и не переименованный полный GREEN.

Архивные записи этого этапа в `android/app/build/reports/android-preview/`:

- `handoff.json` — фактический статус **`blocked-lint`**, APK properties, SHA-256, результаты тестов, сравнение двух сборок и пути к логам; `FullReleaseGatePassed=false`, `FullValidatorPassed=false`.
- `apk-manifest.xml`, `debuggable.txt`, `unsigned-apksigner.txt`, `zipalign.txt` — APK inspection. `apksigner verify` завершился ожидаемым кодом `1` / `Missing META-INF/MANIFEST.MF`; `zipalign -c -P 16 4` — кодом `0`.
- `tooling-tests.json`, `source-validation.json`, `dependency-inventory-comparison.json` — тогдашние 18 tooling checks, 11 source/resource контрастных проверок и сравнение data-only inventories. Это не отчёты об успешном полном release gate; они сохраняются как история до 63/64-check расширения и не заменяют `tooling-final.json`.

JUnit XML находятся в `android/app/build/test-results/testReleaseUnitTest/`: 9 `EndpointTest`, 43 `EndpointInvalidTest`, 10 `BrowserPolicyTest`; failures/errors/skipped — `0`.

Фактические входы: Temurin `17.0.20.1+1`, SDK `platforms;android-37.0` revision `2`, Build Tools `36.0.0`, command-line tools `19.0`, Windows AAPT2 `9.3.3-15703166`.

Локальные toolchain roots и полные **неуспешные** gate logs:

```text
%LOCALAPPDATA%\Temp\opencode\math-ege-android-preview-6b03091ffb374e9aa0a1e4c03f55ac41
  release-build-20261105-183652.log
  release-lock-capture.log (успешный capture, не полный gate)

%LOCALAPPDATA%\Temp\opencode\math-ege-android-preview-repro-e1f86b24c8b04d6aa7d36a1e6fd18a28
  release-build-20261105-183942.log
  strict-data-resolution.log
  strict-manifest-symbols-resolution.log
```

В каждом root сохранён `toolchain.json`; bootstrap сверял официальный ZIP до исполнения. Эти временные файлы, APK и build reports не являются исходниками для release commit.

## Подпись и передача APK

Локальный unsigned gate завершён без изменения закреплённых версий. Для подписи используется уже существующий внешний закрытый preview-keystore **вне Git**:
`%LOCALAPPDATA%\Temp\opencode\math-ege-preview-signing-a8bfcaae16af4acfb573d9eda997f09c`
(ACL только текущий пользователь Windows и `SYSTEM`, RSA 3072, SHA-256 публичного сертификата
`e17ebff9a819267517c7605e437482fc31434b166f47145f30776c4fb44231b7`). Новый ключ не создаётся.

В `%LOCALAPPDATA%\Temp\opencode\completion-android-signed-c921e34de4cb41bab4e1a9cac57b10aa`
фактический unsigned APK выровнен (`zipalign -P 16 -v 4`) без перезаписи исходного файла и подписан v1/v2/v3 для `minSdk 23`; пароль в `finally` очищен из окружения процесса. Строгая проверка `apksigner verify --verbose --print-certs -Werr --min-sdk-version 23` вернула **exit 1** из-за 20 предупреждений `META-INF/... not protected by signature` при `Verifies`, `v1/v2/v3=true`, одном подписанте и ожидаемом отпечатке сертификата. Этот исходный RED сохранён, не переименован в GREEN.

После независимого read-only разбора AOSP/apksig принята только [точная preview-политика](android-signature-policy.md), не общее игнорирование предупреждений. API 23 installer не проверяет содержимое обычных META-INF metadata entries; v2/v3 защищают их на поддерживающих платформах. Это подтверждённая ограниченная потеря целостности метаданных на API 23, а не доказанный runtime exploit приложения. Полный код зависимостей не аудирован. При установке нужно сверить SHA-256 с доверенным private release record; проверка не устраняет само ограничение API 23.

`verify-signed.ps1` в той же внешней директории выполнил отдельный финальный read-only gate,
его результат `signed-result.json` и логи сохранены в
`verification-f5339a2e44234b5f880b48aa0801a229/`:

| Проверка | Факт |
| --- | --- |
| Raw API 23+ warning-strict | exit 1, `Verifies`, v1/v2/v3 true, только точные 20 предупреждений; RED сохранён |
| API 23+ standard + exact-warning set | exit 0; ровно 20 полных literal warnings без новых/пропущенных/повторных/изменённых |
| API 24+ warning-strict | exit 0; v2/v3 true, 0 warnings/errors; v1 false означает отсутствие проверки v1 для выбранного диапазона |
| `zipalign -c -P 16 -v 4` подписанного файла | exit 0 |
| Manifest / analyzer debuggable | `ru.mathege.preview`, code 1, `0.1.0-preview`, min/target 23/37, `false`; backup/cleartext запрещены |
| Компоненты/permissions | одна exported launcher Activity, 0 provider/receiver/service/alias/JNI; только signature-only AndroidX permission |
| Payload / JAR records | все 48 исходных ZIP entries, включая META-INF, имеют те же content SHA-256, длины и compressed lengths; добавлены только `.SF`, `.RSA`, `MANIFEST.MF`; 48 manifest digests и `X-Android-APK-Signed: 2, 3` проверены |
| Сохранность | unsigned/aligned APK совпадают с исходным hash; private key/password files не менялись за время проверки, ACL user/SYSTEM; пароль не расшифровывался повторно, переменная окружения отсутствует |

Итоговый signed APK: **90 065 байт**, SHA-256
`42199293d99b16b7003e7450e3f92a071b5971795c06c74c9ea340000f009dfd`.
Новая подпись, новый ключ, удаление META-INF, пересборка и установка не выполнялись.
Android sideloading допускает отдельный self-signed сертификат; публикация в магазине не требуется.

Используется отдельный application ID `ru.mathege.preview`. Для последующих обновлений нужно сохранить тот же ключ и увеличивать `versionCode`. Нельзя подменять preview-подпись стандартным Android debug-keystore.

Device installation, проверка TalkBack/масштаба текста/клавиатуры и полный вход/экспорт/service worker на реальном сервере остаются отдельной проверкой. В рамках этой сборки устройство и публичный сервер не используются.
