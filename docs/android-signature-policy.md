# Android preview: точная политика проверки подписи

Срез: **5 ноября 2026 года**. Политика относится только к существующему
`ru.mathege.preview`, versionCode `1`, versionName `0.1.0-preview`, minSdk `23`,
targetSdk `37`. Это не общий waiver APK-предупреждений, не изменение Android
permission/crypto кода и не production-приёмка. [Полный протокол](android-preview.md).

## Артефакт и доверенная поставка

- Signed APK: **90 065 байт**, SHA-256
  `42199293d99b16b7003e7450e3f92a071b5971795c06c74c9ea340000f009dfd`.
- Один подписант, RSA **3072 бит**, SHA-256 сертификата
  `e17ebff9a819267517c7605e437482fc31434b166f47145f30776c4fb44231b7`.
- Фактический unsigned APK: **78 186 байт**, SHA-256
  `df2b901b34001a73963f03eddf779a95a070c11fba84dce8e42beeeab2c69204`.
- Build Tools **36.0.0**, `apksigner.jar` SHA-256
  `3716d9311e55d2b0918a2fd9d54ba9e406c5f6abeea700b287f11259bc163dec`.

Перед установкой необходимо сверить signed SHA-256 с доверенным private release
record, а не только с файлом checksum, полученным из произвольного источника.
Это дополнительно связывает точные доставленные байты; сам API 23 installer
не обеспечивает описанную ниже проверку ordinary META-INF metadata.

## Почему исходный warning-strict результат остаётся RED

`apksigner verify --verbose --print-certs -Werr --min-sdk-version 23` возвращает
**exit 1** при `Verifies`, v1/v2/v3 true и 20 предупреждениях
`JAR_SIG_UNPROTECTED_ZIP_ENTRY`. Они не означают отсутствия v1 подписи.
Все 20 записей есть в JAR manifest, их digests совпадают; `.RSA` аутентифицирует
`.SF` и manifest. Но Android API 23 при сборе package certificates пропускает
ordinary `META-INF/` contents, поэтому эти metadata bytes не защищены installer
проверкой v1. Добавление ещё digest records это не исправляет.

**Подтверждённое ограничение целостности, low:** изменённая до установки копия
APK может сохранить принимаемый v1 signer при подмене этих metadata entries.
Из этого не следует возможность изменить `classes.dex`, ресурсы или
`AndroidManifest.xml` без ошибки подписи. Все четыре first-party Java-файла
просмотрены: они не читают эти metadata или собственный APK/JAR и не строят из
них исполняемые пути, browser policy или origin. Runtime exploit не показан.
Полный анализ потребителей metadata в транзитивных зависимостях не выполнен.

На API 24+ v2, а на поддерживающих API 28+ v3, защищают ZIP content, central
directory, нормализованный end record и соответствующие signed data.
Невалидная присутствующая stronger signature не должна молча переходить на v1;
`.SF` содержит `X-Android-APK-Signed: 2, 3`. Термин «whole-file scheme» не означает
аутентификацию каждого неизвестного auxiliary signing-block поля. Raw SHA-256
связывает также точную последовательность байтов доставляемого файла.

## Fail-closed gate

1. Исходный API 23+ `-Werr` сохраняется как **RED, exit 1**, без переписывания лога.
   Другие ошибки или отсутствие `Verifies` не являются разрешённым RED.
2. Standard API 23+ verify должен завершиться **exit 0**, подтвердить v1/v2/v3,
   ровно одного signer и указанный certificate SHA-256.
3. Допускаются **ровно 20 полных literal warning lines** ниже: без новых,
   пропущенных, дублированных или изменённых. Генерировать allowlist из нового
   вывода или разрешать `META-INF/*` нельзя. Любое отклонение блокирует.
4. API 24+ `-Werr` независимо требует **exit 0**, v2/v3 true и **0 warnings/errors**.
   v1 false здесь означает «не проверялся в диапазоне», а не «не подписан».
5. Проверяются signed alignment, compiled manifest/`debuggable=false`, все
   **48** исходных entries включая META-INF, JAR digests и final signed SHA-256.
6. Payload, v1 совместимость, signing key и исходный unsigned APK не изменяются.
   Удаление metadata, пересборка, повторная подпись и снятие `-Werr` без пунктов
   1–5 не являются способом выполнить gate.

Полный literal формат каждой допустимой строки:

```text
WARNING: <exact-name> not protected by signature. Unauthorized modifications to this JAR entry will not be detected. Delete or move the entry outside of META-INF/.
```

Только следующие exact names:

```text
META-INF/com/android/build/gradle/app-metadata.properties
META-INF/version-control-info.textproto
META-INF/androidx.activity_activity.version
META-INF/androidx.annotation_annotation-experimental.version
META-INF/androidx.arch.core_core-runtime.version
META-INF/androidx.browser_browser.version
META-INF/androidx.core_core-ktx.version
META-INF/androidx.core_core.version
META-INF/androidx.interpolator_interpolator.version
META-INF/androidx.lifecycle_lifecycle-livedata-core.version
META-INF/androidx.lifecycle_lifecycle-runtime.version
META-INF/androidx.lifecycle_lifecycle-viewmodel-savedstate.version
META-INF/androidx.lifecycle_lifecycle-viewmodel.version
META-INF/androidx.profileinstaller_profileinstaller.version
META-INF/androidx.savedstate_savedstate.version
META-INF/androidx.startup_startup-runtime.version
META-INF/androidx.tracing_tracing.version
META-INF/androidx.versionedparcelable_versionedparcelable.version
META-INF/kotlinx_coroutines_android.version
META-INF/kotlinx_coroutines_core.version
```

Reviewed original `signature-verification.log` SHA-256:
`2bdec83cb7c74a29778e0602a32606658f4f4003bae00a70c76ceed557aaa444`.
Read-only triage и финальный verifier сохраняются вне Git в
`%LOCALAPPDATA%\Temp\opencode\completion-android-signed-c921e34de4cb41bab4e1a9cac57b10aa`:
`apk-warning-triage-handoff.md`, `verify-signed.ps1` и
`verification-f5339a2e44234b5f880b48aa0801a229/signed-result.json`.

## Диапазоны и ограничения инструмента

Отдельный диагностический `--min-sdk-version 24 --max-sdk-version 27 -Werr`
возвращает предупреждение о ссылке v2 signer на scheme ID 3: verifier ограничил
свою supported-scheme map API 27. Этот результат не включается в allowlist
metadata и не означает отсутствия v3. Основной API 24+ gate без искусственного
верхнего ограничения прошёл без предупреждений.

Проверка выполнена моделью платформ в SDK 36 verifier с его default highest
possible API, не физической установкой на все Android-версии и не API 37
device certification. Полная воспроизводимая привязка бинарного verifier к
source commit не установлена; его точный JAR hash записан.

Не проверены устройство/OEM, TalkBack, библиотечные runtime consumers,
tampered-specimen installation, живой HTTPS/mail/backend и public deployment.
Политика preview не снимает эти условия или полную предметную/правовую приёмку.

## Официальные основания

- [apksigner CLI](https://developer.android.com/tools/apksigner): диапазон API,
  `--print-certs`, `-Werr`.
- [Signing v2](https://source.android.com/docs/security/features/apksigning/v2) и
  [v3](https://source.android.com/docs/security/features/apksigning/v3): digest
  sections, stripping/fallback и версия платформы.
- [AOSP API 23 PackageParser](https://android.googlesource.com/platform/frameworks/base/+/android-6.0.1_r81/core/java/android/content/pm/PackageParser.java):
  `collectCertificates`, пропуск ordinary META-INF до `loadCertificates`.
- [V1SchemeVerifier](https://android.googlesource.com/platform/tools/apksig/+/refs/heads/main/src/main/java/com/android/apksig/internal/apk/v1/V1SchemeVerifier.java),
  [ApkVerifier](https://android.googlesource.com/platform/tools/apksig/+/refs/heads/main/src/main/java/com/android/apksig/ApkVerifier.java) и
  [ApkSignerTool](https://android.googlesource.com/platform/tools/apksig/+/refs/heads/main/src/apksigner/java/com/android/apksigner/ApkSignerTool.java):
  v1 exclusion, `JAR_SIG_UNPROTECTED_ZIP_ENTRY`, range selection и warning-strict
  exit logic. Main-branch ссылки могут измениться; exact SDK bytecode был также
  разобран `javap` и согласован с механизмами этих источников.
