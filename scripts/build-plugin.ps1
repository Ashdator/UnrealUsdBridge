[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$EngineRoot,
    [string]$PackageDirectory
)
$ErrorActionPreference = 'Stop'
$taskRepository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskEngine = (Resolve-Path -LiteralPath $EngineRoot).ProviderPath
$taskRunner = Join-Path $taskEngine 'Engine/Build/BatchFiles/RunUAT.bat'
$taskPlugin = Join-Path $taskRepository 'UnrealUsdBridge/UnrealUsdBridge.uplugin'
if (-not (Test-Path -LiteralPath $taskRunner -PathType Leaf)) { throw 'EngineRoot must contain Engine/Build/BatchFiles/RunUAT.bat.' }
if (-not $PackageDirectory) { $PackageDirectory = Join-Path $taskRepository ('build/UnrealUsdBridge-0.6.6-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
$taskOutput = [IO.Path]::GetFullPath($PackageDirectory)
# Unreal BuildPlugin clears its package destination: require a new folder.
if (Test-Path -LiteralPath $taskOutput) { throw 'Choose a new package folder. Existing destinations are not overwritten.' }
$taskPluginFolder = [IO.Path]::GetFullPath((Join-Path $taskRepository 'UnrealUsdBridge')).TrimEnd('\')
if ($taskOutput.Equals($taskRepository,[StringComparison]::OrdinalIgnoreCase) -or $taskOutput.Equals($taskPluginFolder,[StringComparison]::OrdinalIgnoreCase) -or $taskOutput.StartsWith($taskPluginFolder + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'The package destination must be outside the source plugin folder.' }
& $taskRunner BuildPlugin "-Plugin=$taskPlugin" "-Package=$taskOutput" -TargetPlatforms=Win64
if ($LASTEXITCODE -ne 0) { throw "Plugin build failed with exit code $LASTEXITCODE." }
Write-Output "Built plugin: $taskOutput"
