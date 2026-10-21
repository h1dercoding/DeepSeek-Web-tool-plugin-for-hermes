param(
    [string]$HermesHome = $env:HERMES_HOME
)

$ErrorActionPreference = 'Stop'
Get-Command hermes -ErrorAction Stop | Out-Null

if (-not $HermesHome) {
    $HermesHome = Join-Path $env:LOCALAPPDATA 'hermes'
}
$HermesHome = (Resolve-Path -LiteralPath $HermesHome).Path
$configPath = Join-Path $HermesHome 'config.yaml'
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw "Hermes config not found: $configPath"
}

$files = @('__init__.py', 'provider.py', 'plugin.yaml')
foreach ($name in $files) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $name) -PathType Leaf)) {
        throw "Missing plugin source file: $name"
    }
}

$pluginPath = Join-Path $HermesHome 'plugins\web\deepseek'
$backupPath = Join-Path $HermesHome ('backups\deepseek-web-tool-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
New-Item -ItemType Directory -Path $backupPath | Out-Null
Copy-Item -LiteralPath $configPath -Destination (Join-Path $backupPath 'config.yaml')
if (Test-Path -LiteralPath $pluginPath) {
    Copy-Item -LiteralPath $pluginPath -Destination (Join-Path $backupPath 'deepseek') -Recurse
}
New-Item -ItemType Directory -Path $pluginPath -Force | Out-Null
foreach ($name in $files) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $pluginPath $name) -Force
}

$previousHome = $env:HERMES_HOME
try {
    $env:HERMES_HOME = $HermesHome
    & hermes plugins enable web-deepseek --no-allow-tool-override
    if ($LASTEXITCODE -ne 0) { throw 'Could not enable web-deepseek.' }
    foreach ($key in @('web.search_backend', 'web.extract_backend')) {
        & hermes config set $key deepseek
        if ($LASTEXITCODE -ne 0) { throw "Could not set $key. Backup: $backupPath" }
    }
}
finally {
    $env:HERMES_HOME = $previousHome
}

Write-Output "Installed: $pluginPath"
Write-Output "Backup: $backupPath"
Write-Output 'Restart running Hermes sessions or the gateway to load the plugin.'
