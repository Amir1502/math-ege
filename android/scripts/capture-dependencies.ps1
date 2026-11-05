[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ToolchainState,
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$AllowMetadataUpdate
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'toolchain-common.ps1')
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
$state = Get-PreviewToolchain -StatePath $ToolchainState -ProjectRoot $ProjectRoot
$destination = Join-Path $ProjectRoot 'gradle\verification-metadata.xml'
if ((Test-Path -LiteralPath $destination) -and -not $AllowMetadataUpdate) {
    throw 'Verification metadata already exists. A reviewed update requires -AllowMetadataUpdate; ordinary builds must not regenerate it.'
}
$env:JAVA_HOME = $state.JavaHome
$env:GRADLE_USER_HOME = $state.GradleUserHome
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'tooling\dependency-bootstrap.gradle') -Destination (Join-Path $state.DependencyProject 'build.gradle')
$arguments = @('--no-daemon', '--console=plain', '--max-workers=2', '-g', $state.GradleUserHome,
    '-p', $state.DependencyProject, '--write-verification-metadata', 'sha256', 'resolveArtifacts')
$logPath = Join-Path $state.Root ('dependency-resolution-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '.log')
$result = Invoke-PreviewCommand -Executable $state.GradleExecutable -Arguments $arguments `
    -LogPath $logPath

$inventoryPath = Join-Path $state.DependencyProject 'build\reports\dependencies\artifacts.json'
$inventory = [IO.File]::ReadAllText($inventoryPath) | ConvertFrom-Json
$pins = @{
    'gradle-9.3.3.jar' = '5b30e0ba8f3304f95529f1326668ef16497a736838c90a68815a4211ee65b02d'
    'browser-1.10.0.aar' = 'fb40d1ee5fd910c9d112200868a9534156a7a999abc28fbb3c6815a2e3ac5150'
}
foreach ($name in $pins.Keys) {
    $artifacts = @($inventory | Where-Object { $_.fileName -ceq $name })
    if ($artifacts.Count -eq 0 -or @($artifacts | Where-Object { $_.sha256 -cne $pins[$name] }).Count -gt 0) {
        throw "Primary official Maven artifact checksum verification failed: $name."
    }
    Write-Host "Verified primary Maven artifact: $name $($pins[$name])"
}
$generated = Join-Path $state.DependencyProject 'gradle\verification-metadata.xml'
Assert-PreviewDependencyMetadata -Path $generated
Copy-Item -LiteralPath $generated -Destination $destination
Write-Host "Strict verification metadata: $destination"
Write-Host "Artifact inventory: $inventoryPath"
Write-Host "Resolution log: $($result.LogPath)"
