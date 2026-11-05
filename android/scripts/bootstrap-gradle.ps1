[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ToolchainRoot = (Join-Path $env:LOCALAPPDATA ('Temp\opencode\math-ege-android-' + [guid]::NewGuid().ToString('N'))),
    [string]$JavaHome = $env:JAVA_HOME
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-StrictMode -Version Latest

$version = '9.5.1'
$zipSha256 = 'bafc141b619ad6350fd975fc903156dd5c151998cc8b058e8c1044ab5f7b031f'
$wrapperSha256 = '497c8c2a7e5031f6aa847f88104aa80a93532ec32ee17bdb8d1d2f67a194a9c7'
$distributionUrl = "https://services.gradle.org/distributions/gradle-$version-bin.zip"
$approvedRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Temp\opencode'))
$ToolchainRoot = [IO.Path]::GetFullPath($ToolchainRoot)
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)

if (-not $ToolchainRoot.StartsWith($approvedRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'ToolchainRoot must be a new directory under LocalAppData\Temp\opencode.'
}
if (Test-Path -LiteralPath $ToolchainRoot) {
    throw 'Refusing to trust or overwrite an existing toolchain directory. Choose a fresh directory.'
}
if (-not $JavaHome -or -not (Test-Path -LiteralPath (Join-Path $JavaHome 'bin\javac.exe'))) {
    throw 'JAVA_HOME must identify a JDK 17 installation.'
}
$release = [IO.File]::ReadAllText((Join-Path $JavaHome 'release'))
if ($release -notmatch '(?m)^JAVA_VERSION="17(?:\.[^"]+)?"\r?$') {
    throw 'This project requires JDK 17, not another Java major version.'
}
foreach ($name in @('GRADLE_OPTS', 'JAVA_OPTS', 'JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS')) {
    if ([Environment]::GetEnvironmentVariable($name, 'Process')) {
        throw "Unset $name before running the isolated toolchain. Its value is not logged."
    }
}

$env:JAVA_HOME = $JavaHome
$gradleUserHome = Join-Path $ToolchainRoot 'gradle-user-home'
$env:GRADLE_USER_HOME = $gradleUserHome
[IO.Directory]::CreateDirectory($ToolchainRoot) | Out-Null
$zipPath = Join-Path $ToolchainRoot "gradle-$version-bin.zip"
$logPath = Join-Path $ToolchainRoot 'bootstrap.log'
Start-Transcript -Path $logPath | Out-Null

try {
    $publishedContent = (Invoke-WebRequest -UseBasicParsing -Uri ($distributionUrl + '.sha256')).Content
    $published = if ($publishedContent -is [byte[]]) {
        [Text.Encoding]::ASCII.GetString($publishedContent).Trim()
    } else {
        ([string]$publishedContent).Trim()
    }
    if ($published -ne $zipSha256) {
        throw 'The published Gradle checksum differs from the pinned checksum. Stop and investigate.'
    }
    Invoke-WebRequest -UseBasicParsing -Uri $distributionUrl -OutFile $zipPath
    $actual = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $zipSha256) {
        throw 'Gradle ZIP verification failed. Nothing from this archive will be executed.'
    }
    Write-Host "Verified official Gradle ZIP SHA-256: $actual"
    Expand-Archive -LiteralPath $zipPath -DestinationPath $ToolchainRoot
    $gradle = Join-Path $ToolchainRoot "gradle-$version\bin\gradle.bat"

    $bootstrapProject = Join-Path $ToolchainRoot 'wrapper-bootstrap'
    [IO.Directory]::CreateDirectory($bootstrapProject) | Out-Null
    $utf8 = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText((Join-Path $bootstrapProject 'settings.gradle'), "rootProject.name = 'math-ege-wrapper-bootstrap'`n", $utf8)
    [IO.File]::WriteAllText((Join-Path $bootstrapProject 'build.gradle'), "// Only the built-in verified Gradle wrapper task is used.`n", $utf8)

    & $gradle --no-daemon --console=plain -g $gradleUserHome -p $bootstrapProject wrapper `
        --gradle-version $version --distribution-type bin --gradle-distribution-sha256-sum $zipSha256 --network-timeout 60000
    if ($LASTEXITCODE -ne 0) { throw "Wrapper generation failed with exit code $LASTEXITCODE." }

    $generatedJar = Join-Path $bootstrapProject 'gradle\wrapper\gradle-wrapper.jar'
    $actualWrapper = (Get-FileHash -LiteralPath $generatedJar -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualWrapper -ne $wrapperSha256) {
        throw 'Generated Gradle wrapper JAR does not match the official published checksum.'
    }
    foreach ($relative in @('gradlew', 'gradlew.bat', 'gradle\wrapper\gradle-wrapper.jar')) {
        $destination = Join-Path $ProjectRoot $relative
        if (Test-Path -LiteralPath $destination) {
            if ($relative.EndsWith('.jar')) {
                $matches = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -eq $wrapperSha256
            } else {
                $existing = [IO.File]::ReadAllText($destination).Replace("`r`n", "`n")
                $generated = [IO.File]::ReadAllText((Join-Path $bootstrapProject $relative)).Replace("`r`n", "`n")
                $matches = $existing -ceq $generated
            }
            if (-not $matches) { throw "Refusing to overwrite a wrapper file that differs from the verified generator: $destination." }
            Write-Host "Existing official wrapper preserved: $relative"
            continue
        }
        [IO.Directory]::CreateDirectory((Split-Path -Parent $destination)) | Out-Null
        Copy-Item -LiteralPath (Join-Path $bootstrapProject $relative) -Destination $destination
    }
    Write-Host "Verified generated wrapper JAR SHA-256: $actualWrapper"

    $dependencyProject = Join-Path $ToolchainRoot 'dependency-bootstrap'
    [IO.Directory]::CreateDirectory($dependencyProject) | Out-Null
    [IO.File]::WriteAllText((Join-Path $dependencyProject 'settings.gradle'), "rootProject.name = 'math-ege-dependency-bootstrap'`n", $utf8)
    Copy-Item -LiteralPath (Join-Path $ProjectRoot 'tooling\dependency-bootstrap.gradle') -Destination (Join-Path $dependencyProject 'build.gradle')

    $state = [ordered]@{
        GradleVersion = $version
        GradleZip = $zipPath
        GradleZipSha256 = $actual
        WrapperJarSha256 = $actualWrapper
        GradleExecutable = $gradle
        GradleUserHome = $gradleUserHome
        JavaHome = $JavaHome
        DependencyProject = $dependencyProject
        BootstrapLog = $logPath
    }
    $statePath = Join-Path $ToolchainRoot 'toolchain.json'
    [IO.File]::WriteAllText($statePath, ($state | ConvertTo-Json), $utf8)
    Write-Host "Toolchain state: $statePath"
    Write-Host "Fresh isolated GRADLE_USER_HOME: $gradleUserHome"
} finally {
    Stop-Transcript | Out-Null
}
