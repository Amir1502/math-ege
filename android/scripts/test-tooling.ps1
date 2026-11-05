[CmdletBinding()]
param([string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot))

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'toolchain-common.ps1')
$metadataPath = Join-Path $ProjectRoot 'gradle\verification-metadata.xml'
Assert-PreviewDependencyMetadata -Path $metadataPath
$original = [IO.File]::ReadAllText($metadataPath)
[xml]$lintPolicy = [IO.File]::ReadAllText((Join-Path $ProjectRoot 'gradle\wrapper\lint.xml'))
$lintRules = @($lintPolicy.SelectNodes('/lint/*'))
if ($lintRules.Count -ne 1 -or $lintRules[0].LocalName -cne 'issue' `
        -or $lintRules[0].GetAttribute('id') -cne 'AndroidGradlePluginVersion' `
        -or $lintRules[0].GetAttribute('severity') -cne 'information' `
        -or $lintRules[0].SelectNodes('*').Count -ne 0) {
    throw 'Only a retained wrapper-local version-availability advisory is informational.'
}
$root = Join-Path $env:LOCALAPPDATA ('Temp\opencode\math-ege-android-tooling-tests-' + [guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root) | Out-Null
$utf8 = New-Object Text.UTF8Encoding($false)
$checks = 2

function Assert-Rejected {
    param([string]$Name, [scriptblock]$Action)
    $rejected = $false
    try { & $Action } catch { $rejected = $true }
    if (-not $rejected) { throw "Fail-closed regression: $Name was accepted." }
}

$cases = [ordered]@{
    'metadata-verification-disabled' = $original.Replace('<verify-metadata>true</verify-metadata>', '<verify-metadata>false</verify-metadata>')
    'trusted-artifact-bypass' = $original.Replace('</configuration>', '<trusted-artifacts><trust group=".*" regex="true" /></trusted-artifacts></configuration>')
    'missing-artifact-hash' = ([regex]::new('<sha256\b[^>]*/>')).Replace($original, '', 1)
    'invalid-hash-format' = ([regex]::new('value="[0-9a-f]{64}"')).Replace($original, 'value="invalid"', 1)
    'primary-pin-changed' = $original.Replace('fb40d1ee5fd910c9d112200868a9534156a7a999abc28fbb3c6815a2e3ac5150', ('0' * 64))
}
foreach ($name in $cases.Keys) {
    if ($cases[$name] -ceq $original) { throw "Invalid negative fixture: $name." }
    $path = Join-Path $root ($name + '.xml')
    [IO.File]::WriteAllText($path, $cases[$name], $utf8)
    Assert-Rejected -Name $name -Action { Assert-PreviewDependencyMetadata -Path $path }
    $checks++
}
Assert-Rejected -Name 'missing-native-tool' -Action {
    Invoke-PreviewCommand -Executable (Join-Path $root 'missing.exe') -Arguments @('--version') `
        -LogPath (Join-Path $root 'missing-tool.log') -AllowFailure
}
$checks++
foreach ($value in @('signature', '2', '02', '0x2', '0x02', '0X0002')) {
    if (-not (Test-PreviewSignatureOnlyProtection -Value $value)) {
        throw "Signature-only permission representation was rejected: $value."
    }
    $checks++
}
foreach ($value in @('', 'normal', 'dangerous', 'signatureOrSystem', 'signature|privileged', 'Signature',
        '0', '1', '3', '18', '0x0', '0x1', '0x3', '0x12', ' 2', '2 ', '+2', '-2', '2.0', '2e0',
        '0x', '0x2g', '0x2|0x0', 'signature|signature', '4294967296', '4294967298', '0x100000002', "2`n")) {
    if (Test-PreviewSignatureOnlyProtection -Value $value) {
        throw "Non-signature-only permission representation was accepted: $value."
    }
    $checks++
}
$permission = 'ru.mathege.preview.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION'
foreach ($value in @('signature', '2', '02', '0x2', '0x02', '0X0002')) {
    [xml]$manifest = "<manifest xmlns:android='http://schemas.android.com/apk/res/android'><permission android:name='$permission' android:protectionLevel='$value'/><uses-permission android:name='$permission'/></manifest>"
    $names = Assert-PreviewManifestPermissions -Manifest $manifest
    if ($names.Count -ne 1 -or $names[0] -cne $permission) { throw 'Validated permission names changed.' }
    $checks++
}
$permissionCases = [ordered]@{
    'duplicate-permission-declaration' = "<permission android:name='$permission' android:protectionLevel='2'/><permission android:name='$permission' android:protectionLevel='2'/><uses-permission android:name='$permission'/>"
    'duplicate-permission-use' = "<permission android:name='$permission' android:protectionLevel='2'/><uses-permission android:name='$permission'/><uses-permission-sdk-23 android:name='$permission'/>"
    'undeclared-permission' = "<uses-permission android:name='$permission'/>"
    'permission-with-flags' = "<permission android:name='$permission' android:protectionLevel='0x12'/><uses-permission android:name='$permission'/>"
    'unused-unsafe-permission' = "<permission android:name='$permission' android:protectionLevel='dangerous'/>"
    'unrelated-permission-declaration' = "<permission android:name='fixture.OTHER' android:protectionLevel='2'/>"
    'native-internet-permission' = "<uses-permission android:name='android.permission.INTERNET'/>"
    'permission-tree' = "<permission-tree android:name='$permission'/>"
}
foreach ($name in $permissionCases.Keys) {
    [xml]$manifest = "<manifest xmlns:android='http://schemas.android.com/apk/res/android'>$($permissionCases[$name])</manifest>"
    Assert-Rejected -Name $name -Action { Assert-PreviewManifestPermissions -Manifest $manifest | Out-Null }
    $checks++
}
[xml]$emptyManifest = '<manifest xmlns:android="http://schemas.android.com/apk/res/android"/>'
if ((Assert-PreviewManifestPermissions -Manifest $emptyManifest).Count -ne 0) { throw 'Empty permissions changed.' }
$checks++
$jdk = Join-Path $root 'jdk-fixture'
[IO.Directory]::CreateDirectory((Join-Path $jdk 'bin')) | Out-Null
[IO.File]::WriteAllBytes((Join-Path $jdk 'bin\javac.exe'), [byte[]]@())
[IO.File]::WriteAllText((Join-Path $jdk 'release'), 'JAVA_VERSION="17.0.20"', $utf8)
Assert-PreviewJava17 -JavaHome $jdk
$checks++
foreach ($name in @('GRADLE_OPTS', 'JAVA_OPTS', 'JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS', 'APKANALYZER_OPTS')) {
    $previous = [Environment]::GetEnvironmentVariable($name, 'Process')
    try {
        [Environment]::SetEnvironmentVariable($name, 'fixture-only-never-executed', 'Process')
        Assert-Rejected -Name $name -Action { Assert-PreviewJava17 -JavaHome $jdk }
        $checks++
    } finally { [Environment]::SetEnvironmentVariable($name, $previous, 'Process') }
}
$scripts = @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'scripts') -Filter '*.ps1' -File)
foreach ($file in $scripts) {
    $tokens = $null
    $errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
    if ($errors.Count -ne 0) { throw "PowerShell syntax errors in $($file.Name): $($errors[0].Message)." }
}
$report = [ordered]@{ ChecksPassed = $checks; PowerShellFilesParsed = $scripts.Count; Fixtures = $root }
$reportPath = Join-Path $ProjectRoot 'app\build\reports\android-preview\tooling-tests.json'
[IO.Directory]::CreateDirectory((Split-Path -Parent $reportPath)) | Out-Null
[IO.File]::WriteAllText($reportPath, ($report | ConvertTo-Json), $utf8)
Write-Host "Tooling checks passed: $checks; PowerShell syntax files checked: $($scripts.Count)."
Write-Host "Tooling regression report: $reportPath"
