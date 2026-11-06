[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$JavaHome = $env:JAVA_HOME,
    [string]$AndroidHome = $env:ANDROID_HOME,
    [string]$BuildLog,
    [string]$ToolchainState
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'toolchain-common.ps1')
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
Assert-PreviewJava17 -JavaHome $JavaHome
$env:JAVA_HOME = $JavaHome
if (-not $AndroidHome) { throw 'ANDROID_HOME is required for APK inspection.' }
$AndroidHome = [IO.Path]::GetFullPath($AndroidHome)
$apk = Join-Path $ProjectRoot 'app\build\outputs\apk\release\app-release-unsigned.apk'
$reports = Join-Path $ProjectRoot 'app\build\reports\android-preview'
[IO.Directory]::CreateDirectory($reports) | Out-Null
$apkHash = (Get-FileHash -LiteralPath $apk -Algorithm SHA256).Hash.ToLowerInvariant()
Assert-PreviewDependencyMetadata -Path (Join-Path $ProjectRoot 'gradle\verification-metadata.xml')
$analyzer = Join-Path $AndroidHome 'cmdline-tools\latest\bin\apkanalyzer.bat'
$manifestResult = Invoke-PreviewCommand -Executable $analyzer -Arguments @('manifest', 'print', $apk) `
    -LogPath (Join-Path $reports 'apk-manifest.xml')
[xml]$manifest = $manifestResult.Output
$android = 'http://schemas.android.com/apk/res/android'
$application = $manifest.manifest.application
if ($manifest.manifest.GetAttribute('package') -ne 'ru.mathege.preview') { throw 'Unexpected application ID.' }
foreach ($attribute in @('allowBackup', 'usesCleartextTraffic', 'fullBackupContent')) {
    if ($application.GetAttribute($attribute, $android) -ne 'false') { throw "$attribute must be explicitly false." }
}
if ($application.GetAttribute('debuggable', $android) -notin @('', 'false')) { throw 'APK is debuggable.' }
$debugResult = Invoke-PreviewCommand -Executable $analyzer -Arguments @('manifest', 'debuggable', $apk) `
    -LogPath (Join-Path $reports 'debuggable.txt')
if ($debugResult.Output.Trim() -ne 'false') { throw 'APK analyzer did not confirm debuggable=false.' }
$sdk = $manifest.manifest.'uses-sdk'
if ($sdk.GetAttribute('minSdkVersion', $android) -ne '23' -or $sdk.GetAttribute('targetSdkVersion', $android) -ne '37') {
    throw 'Unexpected minimum/target SDK.'
}
$activities = @($application.SelectNodes('activity'))
$launchers = @($activities | Where-Object { $_.GetAttribute('name', $android) -eq 'ru.mathege.preview.OfflineActivity' `
        -and $_.GetAttribute('exported', $android) -eq 'true' })
if ($activities.Count -ne 2 -or $launchers.Count -ne 1) {
    throw 'Exactly one exported offline launcher and one retained configuration Activity are required.'
}
$legacy = @($activities | Where-Object { $_.GetAttribute('name', $android) -eq 'ru.mathege.preview.MainActivity' `
        -and $_.GetAttribute('exported', $android) -eq 'false' })
if ($legacy.Count -ne 1) { throw 'The retained configuration Activity must not be exported.' }
$components = $application.SelectNodes('activity|activity-alias|receiver|service|provider')
if (@($components | Where-Object { $_.GetAttribute('exported', $android) -eq 'true' }).Count -ne 1) {
    throw 'Another component is exported.'
}
if ($application.SelectNodes('provider|receiver').Count -ne 0) {
    throw 'Unused startup/profiling providers or receivers must not enter the launcher.'
}
$filters = @($launchers[0].SelectNodes('intent-filter'))
if ($filters.Count -ne 1 -or $filters[0].SelectNodes('data').Count -ne 0) { throw 'Unexpected link capture or launcher filters.' }
$actions = @($filters[0].SelectNodes('action') | ForEach-Object { $_.GetAttribute('name', $android) })
$categories = @($filters[0].SelectNodes('category') | ForEach-Object { $_.GetAttribute('name', $android) })
if ($actions.Count -ne 1 -or $actions[0] -ne 'android.intent.action.MAIN' `
        -or $categories.Count -ne 1 -or $categories[0] -ne 'android.intent.category.LAUNCHER') {
    throw 'Launcher must not capture web links.'
}
$permissions = Assert-PreviewManifestPermissions -Manifest $manifest

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead($apk)
try {
    if (@($archive.Entries | Where-Object { $_.FullName -match '^META-INF/.*\.(RSA|DSA|EC)$' }).Count -ne 0) {
        throw 'APK unexpectedly contains a v1 signing certificate.'
    }
    if (@($archive.Entries | Where-Object { $_.FullName -match '^lib/.*\.so$' }).Count -ne 0) {
        throw 'This native-Java launcher must not contain JNI libraries.'
    }
    $offlineRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot '..\frontend\dist-offline'))
    $bundled = @('offline.html', 'offline-compatibility.js', 'course/profile.json', 'course/lessons.json',
        'course/tasks.json', 'course/manifest.json')
    $offlineEntries = @($archive.Entries | Where-Object { $_.FullName -like 'assets/www/*' }).Count
    if ($offlineEntries -lt $bundled.Count) { throw 'Packaged offline assets are incomplete.' }
    foreach ($relative in $bundled) {
        $entry = $archive.GetEntry('assets/www/' + $relative.Replace('\', '/'))
        if ($null -eq $entry) { throw "Missing bundled offline asset: $relative." }
        $sourcePath = Join-Path $offlineRoot $relative
        if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
            throw 'Build the offline frontend (npm run build:offline) before the Android gate.'
        }
        $stream = $entry.Open()
        try {
            $sha = [Security.Cryptography.SHA256]::Create()
            try { $actual = ([BitConverter]::ToString($sha.ComputeHash($stream)) -replace '-', '').ToLowerInvariant() }
            finally { $sha.Dispose() }
        } finally { $stream.Dispose() }
        if ($actual -ne (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()) {
            throw "Bundled offline asset differs from the built package: $relative."
        }
    }
} finally { $archive.Dispose() }
$bytes = [IO.File]::ReadAllBytes($apk)
$end = -1
for ($index = $bytes.Length - 22; $index -ge [Math]::Max(0, $bytes.Length - 65557); $index--) {
    if ([BitConverter]::ToUInt32($bytes, $index) -eq 0x06054b50 `
            -and [BitConverter]::ToUInt16($bytes, $index + 20) -eq $bytes.Length - $index - 22) {
        $end = $index
        break
    }
}
if ($end -lt 0) { throw 'APK ZIP end record is missing.' }
$directoryOffset = [BitConverter]::ToUInt32($bytes, $end + 16)
if ($directoryOffset -lt 16 -or $directoryOffset -ge $bytes.Length) { throw 'Unexpected APK ZIP directory.' }
if ([Text.Encoding]::ASCII.GetString($bytes, $directoryOffset - 16, 16) -eq 'APK Sig Block 42') {
    throw 'APK unexpectedly contains an APK Signing Block.'
}
$signature = Invoke-PreviewCommand -Executable (Join-Path $AndroidHome 'build-tools\36.0.0\apksigner.bat') `
    -Arguments @('verify', '--verbose', $apk) -LogPath (Join-Path $reports 'unsigned-apksigner.txt') -AllowFailure
if ($signature.ExitCode -eq 0 -or $signature.Output -notmatch 'Missing META-INF/MANIFEST\.MF|No signatures') {
    throw 'Expected explicit unsigned-APK evidence was not returned by apksigner.'
}
$alignment = Invoke-PreviewCommand -Executable (Join-Path $AndroidHome 'build-tools\36.0.0\zipalign.exe') `
    -Arguments @('-c', '-P', '16', '4', $apk) -LogPath (Join-Path $reports 'zipalign.txt')

$testFiles = @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'app\build\test-results\testReleaseUnitTest') -Filter 'TEST-*.xml' -File)
$testCount = 0
$classes = @()
foreach ($file in $testFiles) {
    [xml]$tests = [IO.File]::ReadAllText($file.FullName)
    $suite = $tests.testsuite
    if ([int]$suite.failures -ne 0 -or [int]$suite.errors -ne 0 -or [int]$suite.skipped -ne 0) {
        throw "Failed, errored or skipped local tests: $($file.Name)."
    }
    $testCount += [int]$suite.tests
    $classes += [string]$suite.name
}
foreach ($required in @('ru.mathege.preview.EndpointTest', 'ru.mathege.preview.EndpointInvalidTest',
        'ru.mathege.preview.BrowserPolicyTest', 'ru.mathege.preview.OfflineAssetPolicyTest',
        'ru.mathege.preview.OfflineAssetsTest')) {
    if ($classes -notcontains $required) { throw "Missing release unit-test suite: $required." }
}
if ($testCount -eq 0) { throw 'No release unit tests were executed.' }
$lintPath = Join-Path $ProjectRoot 'app\build\reports\lint-results-release.xml'
[xml]$lint = [IO.File]::ReadAllText($lintPath)
if (@($lint.SelectNodes('//issue') | Where-Object { $_.severity -in @('Error', 'Fatal', 'Warning') }).Count -ne 0) {
    throw 'Android lint contains errors or warnings.'
}

[xml]$layout = [IO.File]::ReadAllText((Join-Path $ProjectRoot 'app\src\main\res\layout\activity_main.xml'))
$field = $layout.SelectSingleNode('//EditText')
if ($field.GetAttribute('saveEnabled', $android) -ne 'false' -or $field.HasAttribute('text', $android)) {
    throw 'The first-run endpoint must be empty and must not persist unvalidated drafts.'
}
if ($field.GetAttribute('importantForAutofill', $android) -ne 'no' -or $field.HasAttribute('hint', $android)) {
    throw 'The endpoint must opt out of autofill and use its visible label without a competing hint.'
}
if (@($layout.SelectNodes('//TextView') | Where-Object { $_.GetAttribute('labelFor', $android) -eq '@+id/endpoint_input' }).Count -ne 1) {
    throw 'The endpoint needs an explicit visible accessibility label.'
}
[xml]$dimensions = [IO.File]::ReadAllText((Join-Path $ProjectRoot 'app\src\main\res\values\dimens.xml'))
foreach ($name in @('control_height', 'secondary_height')) {
    $value = $dimensions.SelectSingleNode("/resources/dimen[@name='$name']").InnerText
    if ($value -notmatch '^([0-9]+)dp$' -or [int]$Matches[1] -lt 48) { throw 'Native controls must have at least a 48dp minimum height.' }
}
foreach ($button in $layout.SelectNodes('//Button')) {
    if ($button.GetAttribute('layout_height', $android) -ne 'wrap_content' `
            -or $button.GetAttribute('style') -notin @('@style/Widget.Preview.Button.Primary', '@style/Widget.Preview.Button.Secondary')) {
        throw 'Buttons must use accessible native styles and wrap growing text.'
    }
}
$sources = Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'app\src\main\java') -Recurse -Filter '*.java' -File
$forbidden = 'addJavascriptInterface|java\.net\.(URL|URLConnection|HttpURLConnection|Socket)|okhttp|retrofit|DownloadManager|\.warmup\(|getStringExtra\(|getIntent\('
foreach ($source in $sources) {
    if ([IO.File]::ReadAllText($source.FullName) -match $forbidden) { throw "Forbidden network/bridge/intent-input API in $($source.Name)." }
    if ($source.Name -ne 'OfflineActivity.java' -and [IO.File]::ReadAllText($source.FullName) -match 'android\.webkit') {
        throw "WebView must be confined to OfflineActivity.java."
    }
}

function Get-RelativeLuminance {
    param([string]$Hex)
    $values = @()
    foreach ($offset in @(1, 3, 5)) {
        $value = [Convert]::ToInt32($Hex.Substring($offset, 2), 16) / 255.0
        $values += $(if ($value -le 0.04045) { $value / 12.92 } else { [Math]::Pow(($value + 0.055) / 1.055, 2.4) })
    }
    return 0.2126 * $values[0] + 0.7152 * $values[1] + 0.0722 * $values[2]
}
[xml]$palette = [IO.File]::ReadAllText((Join-Path $ProjectRoot 'app\src\main\res\values\colors.xml'))
$colors = @{}
foreach ($color in $palette.resources.color) { $colors[$color.name] = $color.InnerText }
$contrast = @()
foreach ($pair in @(@('ink', 'canvas', 4.5), @('ink_muted', 'canvas', 4.5), @('surface', 'accent', 4.5),
        @('surface', 'accent_pressed', 4.5), @('error', 'surface', 4.5), @('control_border', 'surface', 3.0),
        @('focus', 'surface', 3.0), @('ink', 'accent', 3.0))) {
    $first = Get-RelativeLuminance $colors[$pair[0]]
    $second = Get-RelativeLuminance $colors[$pair[1]]
    $ratio = ([Math]::Max($first, $second) + 0.05) / ([Math]::Min($first, $second) + 0.05)
    if ($ratio -lt $pair[2]) { throw "Insufficient resource-color contrast: $($pair[0]) / $($pair[1])." }
    $contrast += [ordered]@{ Foreground = $pair[0]; Background = $pair[1]; Ratio = [Math]::Round($ratio, 2); Required = $pair[2] }
}
function Get-CompositedColor {
    param([string]$Overlay, [string]$Background)
    $alpha = [Convert]::ToInt32($Overlay.Substring(1, 2), 16) / 255.0
    $channels = @()
    foreach ($offset in @(0, 2, 4)) {
        $foregroundChannel = [Convert]::ToInt32($Overlay.Substring(3 + $offset, 2), 16)
        $backgroundChannel = [Convert]::ToInt32($Background.Substring(1 + $offset, 2), 16)
        $channels += [int][Math]::Round($foregroundChannel * $alpha + $backgroundChannel * (1 - $alpha))
    }
    return '#{0:x2}{1:x2}{2:x2}' -f $channels[0], $channels[1], $channels[2]
}
foreach ($state in @(@('primary-active-ripple', 'surface', 'ripple_primary', 'accent_pressed'),
        @('primary-release-ripple', 'surface', 'ripple_primary', 'accent'),
        @('secondary-active-ripple', 'accent_pressed', 'ripple_accent', 'accent_soft'))) {
    $background = Get-CompositedColor $colors[$state[2]] $colors[$state[3]]
    $first = Get-RelativeLuminance $colors[$state[1]]
    $second = Get-RelativeLuminance $background
    $ratio = ([Math]::Max($first, $second) + 0.05) / ([Math]::Min($first, $second) + 0.05)
    if ($ratio -lt 4.5) { throw "Insufficient contrast at maximum ripple opacity: $($state[0])." }
    $contrast += [ordered]@{ State = $state[0]; Foreground = $state[1]; Background = $background; Ratio = [Math]::Round($ratio, 2); Required = 4.5 }
}
if ($BuildLog -and ([IO.File]::ReadAllText($BuildLog) -notmatch 'BUILD SUCCESSFUL')) { throw 'The supplied build log does not show a successful Gradle gate.' }
if ((Get-FileHash -LiteralPath $apk -Algorithm SHA256).Hash.ToLowerInvariant() -ne $apkHash) { throw 'APK changed during validation.' }
$report = [ordered]@{
    ValidatedAtUtc = [DateTime]::UtcNow.ToString('o')
    Apk = $apk
    ApkSha256 = $apkHash
    ApkBytes = (Get-Item -LiteralPath $apk).Length
    ApplicationId = 'ru.mathege.preview'
    MinSdk = 23
    TargetSdk = 37
    Debuggable = $false
    Signed = $false
    NativeInternetPermission = $false
    NativePermissions = $permissions
    ExportedComponents = @('ru.mathege.preview.OfflineActivity')
    VerifiedOfflineAssets = 6
    PackagedOfflineEntries = $offlineEntries
    LocalUnitTests = $testCount
    LintErrorsAndWarnings = 0
    LintInformational = @($lint.SelectNodes('//issue') | Where-Object { $_.severity -eq 'Hint' } | ForEach-Object {
        [ordered]@{ Id = [string]$_.id; Severity = [string]$_.severity; Message = [string]$_.message }
    })
    NativeLibraries = 0
    AlignmentVerified = ($alignment.ExitCode -eq 0)
    ResourceContrast = $contrast
    WrapperJarSha256 = (Get-FileHash -LiteralPath (Join-Path $ProjectRoot 'gradle\wrapper\gradle-wrapper.jar') -Algorithm SHA256).Hash.ToLowerInvariant()
    DependencyMetadataSha256 = (Get-FileHash -LiteralPath (Join-Path $ProjectRoot 'gradle\verification-metadata.xml') -Algorithm SHA256).Hash.ToLowerInvariant()
    BuildLog = $BuildLog
    ToolchainState = $ToolchainState
    JavaHome = $JavaHome
    AndroidHome = $AndroidHome
    NotAssessed = @('Device installation/rendering/TalkBack/large fonts/IME', 'Live server/TLS reachability', 'Browser/profile continuity on device', 'Authentication/email/export/service worker', 'Coordinator signing and final signed APK')
}
$reportPath = Join-Path $reports 'validation.json'
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($reportPath, ($report | ConvertTo-Json -Depth 6), $utf8)
Write-Host "Unsigned APK SHA-256: $apkHash"
Write-Host "Passing local release tests: $testCount; lint errors/warnings: 0"
Write-Host "Local validation report: $reportPath"
