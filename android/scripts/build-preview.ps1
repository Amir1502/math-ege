[CmdletBinding()]
param(
    [string]$ToolchainState,
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$JavaHome = $env:JAVA_HOME,
    [string]$AndroidHome = $env:ANDROID_HOME,
    [switch]$WriteLocks,
    [switch]$Offline
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'toolchain-common.ps1')
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
if (-not $ToolchainState) {
    if ($Offline) { throw 'An offline build requires an already verified bootstrap state and populated isolated cache.' }
    Assert-PreviewJava17 -JavaHome $JavaHome
    $root = Join-Path $env:LOCALAPPDATA ('Temp\opencode\math-ege-android-' + [guid]::NewGuid().ToString('N'))
    & (Join-Path $PSScriptRoot 'bootstrap-gradle.ps1') -ProjectRoot $ProjectRoot -ToolchainRoot $root -JavaHome $JavaHome
    $ToolchainState = Join-Path $root 'toolchain.json'
}
$state = Get-PreviewToolchain -StatePath $ToolchainState -ProjectRoot $ProjectRoot
if (-not $AndroidHome) { throw 'Set ANDROID_HOME or pass -AndroidHome.' }
$AndroidHome = [IO.Path]::GetFullPath($AndroidHome)
foreach ($relative in @('platforms\android-37.0\android.jar', 'build-tools\36.0.0\aapt2.exe',
        'build-tools\36.0.0\apksigner.bat', 'cmdline-tools\latest\bin\apkanalyzer.bat')) {
    if (-not (Test-Path -LiteralPath (Join-Path $AndroidHome $relative) -PathType Leaf)) {
        throw "Missing pinned Android SDK tool: $relative. Install it from the official SDK before building."
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'gradle\verification-metadata.xml'))) {
    throw 'Strict dependency verification metadata is required. Use the separate reviewed data-only capture procedure first.'
}
Assert-PreviewDependencyMetadata -Path (Join-Path $ProjectRoot 'gradle\verification-metadata.xml')
& (Join-Path $PSScriptRoot 'test-tooling.ps1') -ProjectRoot $ProjectRoot
if (-not $WriteLocks) {
    foreach ($relative in @('buildscript-gradle.lockfile', 'app\gradle.lockfile')) {
        if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $relative))) {
            throw 'Dependency locks are missing. Initial lock capture requires an explicit -WriteLocks build.'
        }
    }
}
$env:JAVA_HOME = $state.JavaHome
$env:ANDROID_HOME = $AndroidHome
$env:ANDROID_SDK_ROOT = $AndroidHome
$env:GRADLE_USER_HOME = $state.GradleUserHome
$logPath = Join-Path $state.Root ('release-build-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '.log')
$arguments = @('--no-daemon', '--console=plain', '--max-workers=2', '--dependency-verification', 'strict',
    '--project-cache-dir', (Join-Path $state.Root 'android-project-cache'), '-g', $state.GradleUserHome, '-p', $ProjectRoot)
if ($WriteLocks) { $arguments += '--write-locks' }
if ($Offline) { $arguments += '--offline' }
$arguments += @(':app:testReleaseUnitTest', ':app:assembleRelease', ':app:lintRelease')
$result = Invoke-PreviewCommand -Executable $state.GradleExecutable -Arguments $arguments -LogPath $logPath
& (Join-Path $PSScriptRoot 'validate-preview.ps1') -ProjectRoot $ProjectRoot -JavaHome $state.JavaHome `
    -AndroidHome $AndroidHome -BuildLog $result.LogPath -ToolchainState $ToolchainState
Write-Host 'Unsigned preview build and local validation completed. Signing and device/server validation are separate.'
