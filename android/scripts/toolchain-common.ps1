# Shared by the preview's local build scripts; no global cache or init script is used.
Set-StrictMode -Version Latest

function Assert-PreviewJava17 {
    param([Parameter(Mandatory = $true)][string]$JavaHome)
    if (-not (Test-Path -LiteralPath (Join-Path $JavaHome 'bin\javac.exe'))) {
        throw 'A full JDK 17 installation is required.'
    }
    $release = [IO.File]::ReadAllText((Join-Path $JavaHome 'release'))
    if ($release -notmatch '(?m)^JAVA_VERSION="17(?:\.[^"]+)?"\r?$') {
        throw 'JAVA_HOME must identify Java 17.'
    }
    foreach ($name in @('GRADLE_OPTS', 'JAVA_OPTS', 'JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS', 'APKANALYZER_OPTS')) {
        if ([Environment]::GetEnvironmentVariable($name, 'Process')) {
            throw "Unset $name before the isolated build. Its value is not logged."
        }
    }
}

function Get-PreviewToolchain {
    param(
        [Parameter(Mandatory = $true)][string]$StatePath,
        [Parameter(Mandatory = $true)][string]$ProjectRoot
    )
    $StatePath = [IO.Path]::GetFullPath($StatePath)
    $root = Split-Path -Parent $StatePath
    $approved = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Temp\opencode'))
    if (-not $root.StartsWith($approved + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Only a verified bootstrap state under LocalAppData\Temp\opencode is accepted.'
    }
    $state = [IO.File]::ReadAllText($StatePath) | ConvertFrom-Json
    $zipHash = 'bafc141b619ad6350fd975fc903156dd5c151998cc8b058e8c1044ab5f7b031f'
    $wrapperHash = '497c8c2a7e5031f6aa847f88104aa80a93532ec32ee17bdb8d1d2f67a194a9c7'
    $expectedPaths = @{
        GradleZip = (Join-Path $root 'gradle-9.5.1-bin.zip')
        GradleExecutable = (Join-Path $root 'gradle-9.5.1\bin\gradle.bat')
        GradleUserHome = (Join-Path $root 'gradle-user-home')
        DependencyProject = (Join-Path $root 'dependency-bootstrap')
    }
    foreach ($key in $expectedPaths.Keys) {
        if ([IO.Path]::GetFullPath($state.$key) -ine $expectedPaths[$key]) {
            throw "Unexpected toolchain path for $key."
        }
    }
    if ($state.GradleVersion -ne '9.5.1' -or $state.GradleZipSha256 -ne $zipHash -or $state.WrapperJarSha256 -ne $wrapperHash) {
        throw 'Toolchain state differs from the pinned version/checksums.'
    }
    if ((Get-FileHash -LiteralPath $state.GradleZip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $zipHash) {
        throw 'Official Gradle ZIP checksum verification failed.'
    }

    # A JSON state or .zip.ok marker is not proof. Recheck the extracted files
    # against the already-hashed official archive before executing Gradle again.
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($state.GradleZip)
    $expectedFiles = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    try {
        foreach ($entry in $archive.Entries) {
            if ($entry.FullName.EndsWith('/')) { continue }
            if (-not $entry.FullName.StartsWith('gradle-9.5.1/')) {
                throw 'Unexpected file in the pinned Gradle archive.'
            }
            $extracted = Join-Path $root $entry.FullName.Replace('/', [IO.Path]::DirectorySeparatorChar)
            [void]$expectedFiles.Add([IO.Path]::GetFullPath($extracted))
            if (-not (Test-Path -LiteralPath $extracted -PathType Leaf)) {
                throw "Missing extracted Gradle file: $($entry.FullName)."
            }
            $stream = $entry.Open()
            $digest = [Security.Cryptography.SHA256]::Create()
            try {
                $expected = ([BitConverter]::ToString($digest.ComputeHash($stream))).Replace('-', '').ToLowerInvariant()
            } finally {
                $digest.Dispose()
                $stream.Dispose()
            }
            if ((Get-FileHash -LiteralPath $extracted -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
                throw "Extracted Gradle file changed: $($entry.FullName)."
            }
        }
    } finally {
        $archive.Dispose()
    }
    foreach ($file in Get-ChildItem -LiteralPath (Join-Path $root 'gradle-9.5.1') -Recurse -File -Force) {
        if (-not $expectedFiles.Contains($file.FullName)) {
            throw "Unexpected file in the verified Gradle distribution: $($file.Name)."
        }
    }
    foreach ($relative in @('init.gradle', 'init.gradle.kts')) {
        if (Test-Path -LiteralPath (Join-Path $state.GradleUserHome $relative)) {
            throw 'User-home init scripts are not allowed in this isolated build.'
        }
    }
    $initDirectory = Join-Path $state.GradleUserHome 'init.d'
    if ((Test-Path -LiteralPath $initDirectory) -and @(Get-ChildItem -LiteralPath $initDirectory -Recurse -File -Force).Count -gt 0) {
        throw 'User-home init.d files are not allowed in this isolated build.'
    }

    $wrapper = Join-Path $ProjectRoot 'gradle\wrapper\gradle-wrapper.jar'
    if ((Get-FileHash -LiteralPath $wrapper -Algorithm SHA256).Hash.ToLowerInvariant() -ne $wrapperHash) {
        throw 'Project wrapper JAR differs from the official checksum.'
    }
    $properties = [IO.File]::ReadAllText((Join-Path $ProjectRoot 'gradle\wrapper\gradle-wrapper.properties'))
    $required = @(
        'distributionBase=GRADLE_USER_HOME',
        'distributionPath=wrapper/dists',
        "distributionSha256Sum=$zipHash",
        'distributionUrl=https\://services.gradle.org/distributions/gradle-9.5.1-bin.zip',
        'networkTimeout=60000',
        'validateDistributionUrl=true',
        'zipStoreBase=GRADLE_USER_HOME',
        'zipStorePath=wrapper/dists'
    )
    $lines = @($properties -split '\r?\n' | Where-Object { $_ -ne '' })
    if (@(Compare-Object $required $lines -CaseSensitive).Count -ne 0) {
        throw 'Wrapper properties differ from the pinned official distribution policy.'
    }
    Assert-PreviewJava17 -JavaHome $state.JavaHome
    $state | Add-Member -NotePropertyName Root -NotePropertyValue $root
    return $state
}

function Assert-PreviewDependencyMetadata {
    param([Parameter(Mandatory = $true)][string]$Path)
    [xml]$metadata = [IO.File]::ReadAllText($Path)
    $ns = New-Object Xml.XmlNamespaceManager($metadata.NameTable)
    $ns.AddNamespace('v', 'https://schema.gradle.org/dependency-verification')
    $verify = $metadata.SelectSingleNode('/v:verification-metadata/v:configuration/v:verify-metadata', $ns)
    $artifacts = $metadata.SelectNodes('//v:artifact', $ns)
    if ($null -eq $verify -or $verify.InnerText -ne 'true' -or $artifacts.Count -eq 0 `
            -or $metadata.SelectNodes('//v:trusted-artifacts/*', $ns).Count -ne 0 `
            -or $metadata.SelectNodes('//v:artifact[not(v:sha256)]', $ns).Count -ne 0) {
        throw 'Dependency metadata must verify metadata, hash every artifact, and contain no trust bypasses.'
    }
    foreach ($checksum in $metadata.SelectNodes('//v:sha256', $ns)) {
        if ($checksum.GetAttribute('value') -cnotmatch '^[0-9a-f]{64}$') {
            throw 'Invalid SHA-256 value in dependency verification metadata.'
        }
    }
    $pins = @(
        @('com.android.tools.build', 'gradle', '9.3.3', 'gradle-9.3.3.jar', '5b30e0ba8f3304f95529f1326668ef16497a736838c90a68815a4211ee65b02d'),
        @('androidx.browser', 'browser', '1.10.0', 'browser-1.10.0.aar', 'fb40d1ee5fd910c9d112200868a9534156a7a999abc28fbb3c6815a2e3ac5150')
    )
    foreach ($pin in $pins) {
        $query = "//v:component[@group='$($pin[0])' and @name='$($pin[1])' and @version='$($pin[2])']/v:artifact[@name='$($pin[3])']/v:sha256"
        $checksums = $metadata.SelectNodes($query, $ns)
        if ($checksums.Count -ne 1 -or $checksums[0].GetAttribute('value') -cne $pin[4]) {
            throw "Primary artifact pin differs from its published checksum: $($pin[3])."
        }
    }
}

function Test-PreviewSignatureOnlyProtection {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)
    if ($Value -ceq 'signature') { return $true }
    [uint32]$level = 0
    $style = [Globalization.NumberStyles]::None
    if ($Value -cmatch '\A0[xX][0-9a-fA-F]+\z') {
        $Value = $Value.Substring(2)
        $style = [Globalization.NumberStyles]::AllowHexSpecifier
    } elseif ($Value -cnotmatch '\A[0-9]+\z') { return $false }
    return [uint32]::TryParse($Value, $style, [Globalization.CultureInfo]::InvariantCulture, [ref]$level) -and $level -eq 2
}

function Assert-PreviewManifestPermissions {
    param([Parameter(Mandatory = $true)][xml]$Manifest)
    $android = 'http://schemas.android.com/apk/res/android'
    $internal = 'ru.mathege.preview.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION'
    $permissions = @($Manifest.SelectNodes('/manifest/uses-permission|/manifest/uses-permission-sdk-23') |
        ForEach-Object { $_.GetAttribute('name', $android) })
    $declared = @($Manifest.SelectNodes('/manifest/permission|/manifest/permission-tree|/manifest/permission-group'))
    if ($permissions.Count -gt 1 -or @($permissions | Where-Object { $_ -cne $internal }).Count -ne 0) {
        throw 'Unexpected or duplicate native permission.'
    }
    if ($declared.Count -gt 1 -or $declared.Count -lt $permissions.Count) {
        throw 'Missing or duplicate internal permission declaration.'
    }
    if ($declared.Count -eq 1 -and ($declared[0].LocalName -cne 'permission' `
            -or $declared[0].GetAttribute('name', $android) -cne $internal `
            -or -not (Test-PreviewSignatureOnlyProtection -Value $declared[0].GetAttribute('protectionLevel', $android)))) {
        throw 'AndroidX internal permission must be exactly signature-only.'
    }
    return ,$permissions
}

function Invoke-PreviewCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$LogPath,
        [switch]$AllowFailure
    )
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        throw "Missing native tool: $Executable."
    }
    [IO.Directory]::CreateDirectory((Split-Path -Parent $LogPath)) | Out-Null
    $lines = New-Object 'System.Collections.Generic.List[string]'
    $previous = $ErrorActionPreference
    try {
        # Windows PowerShell 5.1 represents native stderr as ErrorRecord objects.
        # Capture those without confusing stderr with the native process exit code.
        $ErrorActionPreference = 'Continue'
        & $Executable @Arguments 2>&1 | ForEach-Object {
            $line = $_.ToString()
            $lines.Add($line)
            Write-Host $line
        }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
        $utf8 = New-Object Text.UTF8Encoding($false)
        [IO.File]::WriteAllText($LogPath, (($lines -join "`n") + "`n"), $utf8)
    }
    if ($code -ne 0 -and -not $AllowFailure) {
        throw "Command failed with exit code $code. See $LogPath."
    }
    return [PSCustomObject]@{ ExitCode = $code; Output = ($lines -join "`n"); LogPath = $LogPath }
}
