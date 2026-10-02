param([switch]$SkipInstaller)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if ($projectRoot -ne 'D:\stockswitch') { throw "Unexpected project root: $projectRoot" }
Set-Location -LiteralPath $projectRoot
$env:STOCKSWITCH_DEBUG_BUILD = '0'
function Assert-ProjectDirectory([string]$path) {
    $full = [System.IO.Path]::GetFullPath($path)
    if (-not $full.StartsWith($projectRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside project root: $full"
    }
    if (Test-Path -LiteralPath $full) {
        $item = Get-Item -LiteralPath $full -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing reparse-point directory: $full"
        }
    }
}
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Project virtual environment is missing' }
& $python -m PyInstaller --version
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller is not installed in .venv' }
$version = & $python -c 'from src.app.version import VERSION; print(VERSION)'
if ($LASTEXITCODE -ne 0 -or -not $version) { throw 'Could not read application version' }
$buildDir = Join-Path $projectRoot 'build'
Assert-ProjectDirectory $buildDir
$distDir = Join-Path $projectRoot 'dist'
Assert-ProjectDirectory $distDir
Assert-ProjectDirectory (Join-Path $distDir 'StockSwitch')
$releaseDir = Join-Path $projectRoot 'release'
Assert-ProjectDirectory $releaseDir
if (Test-Path -LiteralPath $buildDir) {
    $resolvedBuild = (Resolve-Path -LiteralPath $buildDir).Path
    if ($resolvedBuild -ne $buildDir) { throw "Unsafe build path: $resolvedBuild" }
    Remove-Item -LiteralPath $resolvedBuild -Recurse -Force
}
New-Item -ItemType Directory -Path (Join-Path $buildDir 'tmp') -Force | Out-Null
$env:TEMP = Join-Path $buildDir 'tmp'
$env:TMP = $env:TEMP
$env:PYINSTALLER_CONFIG_DIR = Join-Path $buildDir 'pyinstaller-cache'
& $python -m scripts.build_resources
if ($LASTEXITCODE -ne 0) { throw 'Resource generation failed' }
& $python -m PyInstaller --noconfirm StockSwitch.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
$exe = Join-Path $projectRoot 'dist\StockSwitch\StockSwitch.exe'
if (-not (Test-Path -LiteralPath $exe) -or (Get-Item -LiteralPath $exe).Length -le 0) {
    throw 'StockSwitch.exe was not created or is empty'
}
$included = Get-ChildItem -LiteralPath (Join-Path $distDir 'StockSwitch') -Recurse -File
$forbidden = $included | Where-Object {
    $_.Extension -in '.py', '.db', '.sqlite', '.sqlite3', '.log' -or
    $_.FullName -match '\\.git\\|\\tests\\|\\\.venv\\'
}
if ($forbidden) { throw "Forbidden source/test/user-data file in distribution: $($forbidden[0].FullName)" }
if (Test-Path -LiteralPath (Join-Path $distDir 'StockSwitch\_internal\icuuc.dll')) {
    throw 'Incompatible build-host ICU leaked into distribution'
}
$gplOnly = $included | Where-Object {
    $_.Name -match '^Qt6(VirtualKeyboard|Graphs|Lottie|NetworkAuth|Quick3D|QuickTimeline).*\.dll$' -or
    $_.FullName -match 'VirtualKeyboard'
}
if ($gplOnly) { throw "Unapproved Qt module leaked into distribution: $($gplOnly[0].FullName)" }
$metadata = (Get-Item -LiteralPath $exe).VersionInfo
if ($metadata.ProductVersion -ne $version -or $metadata.FileVersion -ne $version) {
    throw 'Windows EXE version metadata does not match the application version'
}
New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
$zip = Join-Path $releaseDir "StockSwitch-$version-Windows-x64.zip"
if (Test-Path -LiteralPath $zip) {
    if (((Get-Item -LiteralPath $zip -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing reparse-point ZIP: $zip"
    }
    Remove-Item -LiteralPath $zip -Force
}
Compress-Archive -LiteralPath (Join-Path $projectRoot 'dist\StockSwitch') -DestinationPath $zip
Write-Output "EXE: $exe"
Write-Output "Portable ZIP: $zip"
if (-not $SkipInstaller) {
    $iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($null -eq $iscc) {
        Write-Warning 'Inno Setup Compiler unavailable; installer build not executed.'
    } else {
        & $iscc.Source "/DAppVersion=$version" 'installer\StockSwitch.iss'
        if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed' }
    }
}
